#!/usr/bin/env python3
"""
Unit tests for endpoints/cassandra_store.py (B9 step 1).

The module imports the Cassandra driver and config, neither of which is
available in a bare checkout, so the functions are extracted by AST and run
against a stubbed _build() -- the same pattern as test_reply_scrub.py and
test_location_store.py.

What matters here is the PID guard. The service runs under Gunicorn with
multiple workers; the driver's background threads and sockets do not survive
fork(), so a session inherited by a child is silently dead and its first
query hangs until it times out. Every test below exists because that failure
is invisible in normal operation.

Run as a plain script (pytest is not installed in the Windows venv):

    python tests/test_cassandra_store.py
"""

import ast
import io
import os
import sys
import threading
import logging

HERE = os.path.dirname(os.path.abspath(__file__))
MODULE = os.path.join(HERE, '..', 'endpoints', 'cassandra_store.py')

WANTED = ('_build', 'get_cassandra_session', 'connect_eagerly',
          'session_is_live', '_warm', '_start_warm_thread',
          '_after_fork', 'start_warmup')


def load():
    """Compile the module's functions without importing the driver."""
    src = io.open(MODULE, 'r', newline='', encoding='utf-8').read().replace('\r\n', '\n')
    tree = ast.parse(src)
    kept = [n for n in tree.body
            if isinstance(n, ast.FunctionDef) and n.name in WANTED]
    missing = set(WANTED) - {n.name for n in kept}
    if missing:
        raise AssertionError('cassandra_store is missing %s' % sorted(missing))
    namespace = {
        'logging': logging, 'os': os, 'threading': threading,
        '_cluster': None, '_session': None, '_owner_pid': None,
        '_lock': threading.Lock(),
        '_fork_hook_registered': False, '_warm_thread': None,
        # names _build closes over; never reached once _build is stubbed
        'Cluster': None, 'ExecutionProfile': None, 'EXEC_PROFILE_DEFAULT': None,
        'PlainTextAuthProvider': None, 'ConsistencyLevel': None,
        'TokenAwarePolicy': None, 'DCAwareRoundRobinPolicy': None,
        'CASSANDRA_KEYSPACE': 'k', 'CASSANDRA_CONTACT_POINTS': ['h'],
        'CASSANDRA_PORT': 9042, 'CASSANDRA_USERNAME': 'u',
        'CASSANDRA_PASSWORD': 'p', 'CASSANDRA_LOCAL_DC': 'dc',
    }
    exec(compile(ast.Module(body=kept, type_ignores=[]), MODULE, 'exec'),
         namespace)
    return namespace


class FakeSession(object):
    def __init__(self, tag):
        self.tag = tag
        self.is_shutdown = False


class FakeCluster(object):
    def __init__(self, tag):
        self.tag = tag
        self.shutdown_calls = 0

    def shutdown(self):
        self.shutdown_calls += 1


def fresh(builds=None):
    """A loaded namespace with _build stubbed to hand out numbered sessions."""
    ns = load()
    made = []

    def stub():
        if builds is not None and len(made) >= len(builds):
            return None, None
        if builds is not None and builds[len(made)] is None:
            made.append(None)
            return None, None
        tag = len(made)
        cluster, session = FakeCluster(tag), FakeSession(tag)
        made.append(session)
        return cluster, session

    ns['_build'] = stub
    ns['_made'] = made
    return ns


PASSED = []
FAILED = []


def check(name, condition, detail=''):
    (PASSED if condition else FAILED).append(name)
    print('  %s %s%s' % ('ok ' if condition else '!! ', name,
                         '' if condition else '   <-- ' + detail))


def main():
    print('cassandra_store: session reuse')
    ns = fresh()
    first = ns['get_cassandra_session']()
    check('first call connects', first is not None and first.tag == 0)
    second = ns['get_cassandra_session']()
    check('second call reuses, does not rebuild',
          second is first and len(ns['_made']) == 1,
          '%d builds' % len(ns['_made']))
    check('session_is_live is true once connected', ns['session_is_live']())

    print('')
    print('cassandra_store: a dead session is replaced')
    ns = fresh()
    one = ns['get_cassandra_session']()
    one.is_shutdown = True
    two = ns['get_cassandra_session']()
    check('a shutdown session is rebuilt', two is not one and two.tag == 1)
    check('session_is_live false while shut down',
          (lambda: (setattr(two, 'is_shutdown', True),
                    ns['session_is_live']())[1])() is False)

    print('')
    print('cassandra_store: the fork guard')
    ns = fresh()
    parent = ns['get_cassandra_session']()
    parent_cluster = ns['_cluster']
    # simulate fork: same module state, different process
    ns['_owner_pid'] = ns['_owner_pid'] + 1
    child = ns['get_cassandra_session']()
    check('a session inherited across fork is NOT reused',
          child is not parent,
          'the child reused the parent\'s dead session')
    check('the child reconnects', child is not None and child.tag == 1)
    check('the child does NOT shut down the inherited cluster',
          parent_cluster.shutdown_calls == 0,
          'closing it would break the parent, which still owns those sockets')
    check('the new session is owned by this process',
          ns['_owner_pid'] == os.getpid())
    check('session_is_live true again after reconnect', ns['session_is_live']())

    print('')
    print('cassandra_store: a failed connect')
    ns = fresh(builds=[None])
    none_back = ns['get_cassandra_session']()
    check('returns None rather than raising', none_back is None)
    check('nothing is cached after a failure',
          ns['_session'] is None and ns['_owner_pid'] is None)
    check('session_is_live false when never connected',
          ns['session_is_live']() is False)
    check('connect_eagerly reports False on failure',
          ns['connect_eagerly']() is False)

    print('')
    print('cassandra_store: connect_eagerly')
    ns = fresh()
    check('connect_eagerly returns True and warms the session',
          ns['connect_eagerly']() is True and ns['_session'] is not None)
    check('connect_eagerly is idempotent',
          ns['connect_eagerly']() is True and len(ns['_made']) == 1,
          '%d builds' % len(ns['_made']))

    print('')
    print('cassandra_store: concurrent first use builds exactly one cluster')
    ns = fresh()
    slow_lock = threading.Lock()
    inner = ns['_build']

    def slow():
        with slow_lock:          # serialise the stub so a race is observable
            import time
            time.sleep(0.02)
            return inner()

    ns['_build'] = slow
    out = []
    threads = [threading.Thread(target=lambda: out.append(
        ns['get_cassandra_session']())) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    check('8 threads see one session',
          len({id(o) for o in out}) == 1, '%d distinct' % len({id(o) for o in out}))
    check('8 threads caused one build', len(ns['_made']) == 1,
          '%d builds -- orphaned pools are the bug B9 removes' % len(ns['_made']))

    print('')
    print('cassandra_store: the warm-up thread')
    ns = fresh()
    thread = ns['_start_warm_thread']()
    thread.join(2)
    check('the warm-up thread connects', ns['_session'] is not None)
    check('it is a daemon so it cannot hold the process open', thread.daemon)
    check('it does not raise out of the thread', not thread.is_alive())

    ns = fresh(builds=[None])
    thread = ns['_start_warm_thread']()
    thread.join(2)
    check('a failed warm-up does not raise either',
          not thread.is_alive() and ns['_session'] is None)

    print('')
    print('cassandra_store: the at-fork hook')
    ns = fresh()
    parent = ns['get_cassandra_session']()
    parent_cluster = ns['_cluster']
    old_lock = ns['_lock']
    ns['_after_fork']()
    if ns['_warm_thread'] is not None:
        ns['_warm_thread'].join(2)
    check('the child does not inherit the parent session',
          ns['_session'] is not parent)
    check('the child does not shut down the parent cluster',
          parent_cluster.shutdown_calls == 0)
    check('the child gets a NEW lock object', ns['_lock'] is not old_lock,
          'an inherited lock can be inherited LOCKED and never released')
    check('the child is warm without a request', ns['_session'] is not None)

    print('')
    print('cassandra_store: a lock held at the moment of fork')
    ns = fresh()
    ns['_lock'].acquire()        # as if another thread held it when fork hit
    ns['_after_fork']()
    if ns['_warm_thread'] is not None:
        ns['_warm_thread'].join(2)
    done = threading.Event()

    def call():
        ns['get_cassandra_session']()
        done.set()

    threading.Thread(target=call, daemon=True).start()
    check('the child does NOT deadlock on an inherited held lock',
          done.wait(3),
          'every later request in that worker would block forever')

    print('')
    print('cassandra_store: start_warmup')
    ns = fresh()
    first = ns['start_warmup']()
    if ns['_warm_thread'] is not None:
        ns['_warm_thread'].join(2)
    check('start_warmup warms this process', ns['_session'] is not None)
    check('start_warmup reports the fork hook on a forking platform',
          first == hasattr(os, 'register_at_fork'),
          'should be False only where fork() does not exist (Windows)')
    before = ns['_fork_hook_registered']
    ns['start_warmup']()
    if ns['_warm_thread'] is not None:
        ns['_warm_thread'].join(2)
    check('calling it twice does not register the hook twice',
          ns['_fork_hook_registered'] == before and len(ns['_made']) == 1,
          '%d builds' % len(ns['_made']))

    print('')
    print('=' * 62)
    print('  %d/%d passed' % (len(PASSED), len(PASSED) + len(FAILED)))
    if FAILED:
        for name in FAILED:
            print('    FAILED: %s' % name)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
