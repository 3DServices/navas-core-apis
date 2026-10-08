"""The one Cassandra session for this process.

B9. Six modules -- devices, data, data_handler, device_configs, management
and statistics -- each defined their own get_cassandra_session() over their
own module globals and their own Cluster(). The six implementations were
functionally identical (same auth, protocol_version=4, ConsistencyLevel.ONE,
TokenAwarePolicy over DCAwareRoundRobinPolicy, same contact points, port and
keyspace), so a worker could hold six separate clusters and six separate
connection pools to the same database, each paying its own 6-7 second
handshake the first time something touched it.

This module holds the single implementation. The six keep the name
get_cassandra_session importable by re-exporting it from here, so none of
the 42 call sites had to change.

It is a leaf: it imports config and the driver and nothing from endpoints.
access_guard, alert_engine and waswa_fleet reach the session through a
deferred `from .devices import get_cassandra_session` inside a function
body, which is the tell that a module-level import of devices would be
circular. Importing THIS module at module level is safe from anywhere.

FORK SAFETY
-----------
The service runs under Gunicorn with multiple workers. The driver keeps
background threads and open sockets, and neither survives fork(): a session
inherited by a child process is silently dead, and its first query hangs
until it times out rather than failing fast.

So the session records the pid that created it. A caller in a different
process gets a fresh connection instead of the inherited corpse. That makes
this module correct whether or not Gunicorn runs with preload_app, which is
not something the repository can answer -- there is no gunicorn config in it.

The old, inherited cluster is deliberately NOT shut down from the child:
its sockets belong to the parent, and closing them from here would break the
parent's own session. The child drops its reference and lets the parent own
its lifecycle.

CONTRACT
--------
get_cassandra_session() returns a connected Session, or None if the connect
failed -- exactly what the six implementations returned, so callers that
check for None keep working unchanged. Callers that want the difference
between "could not look" and "nothing was there" should use
location_store.fixes(), which raises PositionsUnavailable.
"""

import logging
import os
import threading

from cassandra.cluster import Cluster, ExecutionProfile, EXEC_PROFILE_DEFAULT
from cassandra.auth import PlainTextAuthProvider
from cassandra import ConsistencyLevel
from cassandra.policies import TokenAwarePolicy, DCAwareRoundRobinPolicy

from config import (
    CASSANDRA_KEYSPACE,
    CASSANDRA_CONTACT_POINTS,
    CASSANDRA_PORT,
    CASSANDRA_USERNAME,
    CASSANDRA_PASSWORD,
    CASSANDRA_LOCAL_DC,
)

_cluster = None
_session = None
_owner_pid = None

# Two threads in the same worker can reach a cold session at once. Without
# this they both build a Cluster and one is orphaned -- a pool leak that
# looks exactly like the problem B9 exists to remove.
_lock = threading.Lock()


def _build():
    """Connect. Returns a Session, or None. Never raises."""
    try:
        auth_provider = PlainTextAuthProvider(
            username=CASSANDRA_USERNAME,
            password=CASSANDRA_PASSWORD,
        )
        profile = ExecutionProfile(
            load_balancing_policy=TokenAwarePolicy(
                DCAwareRoundRobinPolicy(local_dc=CASSANDRA_LOCAL_DC)),
            consistency_level=ConsistencyLevel.ONE,
        )
        cluster = Cluster(
            contact_points=CASSANDRA_CONTACT_POINTS,
            port=CASSANDRA_PORT,
            auth_provider=auth_provider,
            protocol_version=4,
            execution_profiles={EXEC_PROFILE_DEFAULT: profile},
        )
        session = cluster.connect(CASSANDRA_KEYSPACE)
        return cluster, session
    except Exception as error:          # noqa: BLE001 -- matches the old contract
        # The six implementations printed this. Logging keeps it in the
        # service log instead of stdout, and keeps the detail out of any
        # response body: nothing here reaches a caller.
        logging.warning('Cassandra connect failed: %s', error)
        return None, None


def get_cassandra_session():
    """The process's Cassandra session, connecting on first use.

    Returns None when the store cannot be reached, as the six separate
    implementations did.
    """
    global _cluster, _session, _owner_pid

    pid = os.getpid()
    session, owner = _session, _owner_pid

    if session is not None and owner == pid and not session.is_shutdown:
        return session

    with _lock:
        # Re-check: another thread may have connected while we waited.
        if (_session is not None and _owner_pid == pid
                and not _session.is_shutdown):
            return _session

        if _session is not None and _owner_pid != pid:
            # Inherited across fork. Drop the reference without touching the
            # sockets -- they are the parent's.
            logging.info(
                'Cassandra session inherited from pid %s, reconnecting in %s',
                _owner_pid, pid)
            _cluster, _session = None, None

        cluster, session = _build()
        if session is None:
            return None

        _cluster, _session, _owner_pid = cluster, session, pid
        logging.info('Connected to Cassandra cluster (pid %s)', pid)
        return _session


def connect_eagerly():
    """Warm the session now, so the first request does not pay the handshake.

    Safe to call more than once. Must be called AFTER fork -- from a
    Gunicorn post_fork hook, not at import time under preload_app. Returns
    True when a session is available. That caller is B9 step 4 and is not
    wired up yet; nothing calls this today.
    """
    return get_cassandra_session() is not None


def session_is_live():
    """True if this process currently holds a usable session. For checks."""
    return (_session is not None
            and _owner_pid == os.getpid()
            and not _session.is_shutdown)


# ---------------------------------------------------------------------------
# B9 step 4: move the handshake off the request path.
#
# Steps 1-3 made the session correct across fork. They did not make it early:
# the connect still happened on whichever request touched Cassandra first, and
# that request paid 6-7 seconds, or timed out and answered 503. That was
# observed live twice.
#
# The warm-up is in-app rather than in a gunicorn.conf.py post_fork hook, by
# choice, so it needs no change to the Supervisor command line and works the
# same whether Gunicorn runs with preload_app on or off:
#
#   preload_app off (the default) -- each worker imports the app itself, after
#     fork, so start_warmup() runs in the worker and warms that worker.
#
#   preload_app on -- the app is imported once in the master, before fork, so
#     start_warmup() warms the master (harmless, and the master serves nothing)
#     and the registered at-fork hook warms each child as it appears.
#
# Nothing here is on the request path, and nothing here can fail a request: the
# warm-up runs on a daemon thread, and if it fails the ordinary lazy connect
# still happens on first use.
# ---------------------------------------------------------------------------

_fork_hook_registered = False
_warm_thread = None


def _warm():
    """Connect, on a background thread. Never raises into the caller."""
    try:
        if connect_eagerly():
            logging.info('Cassandra warm-up connected (pid %s)', os.getpid())
        else:
            logging.warning(
                'Cassandra warm-up could not connect (pid %s); the first '
                'request that needs it will retry', os.getpid())
    except Exception:                   # noqa: BLE001 -- a daemon thread
        logging.exception('Cassandra warm-up raised (pid %s)', os.getpid())


def _start_warm_thread():
    global _warm_thread
    thread = threading.Thread(target=_warm, name='cassandra-warmup',
                              daemon=True)
    _warm_thread = thread
    thread.start()
    return thread


def _after_fork():
    """Runs in the CHILD right after fork(), while it is still single-threaded.

    Two things have to happen here, and the first is the one that bites.

    A lock is inherited in whatever state it had at the instant of fork. If
    another thread held _lock at that moment, the child inherits it LOCKED and
    nothing can ever release it -- the thread that held it does not exist in
    the child. Every later get_cassandra_session() in that worker would block
    forever on `with _lock:`. So the child gets a new lock, not the parent's.

    Second, the parent's cluster and session belong to the parent. The
    reference is dropped without shutting anything down: those sockets are the
    parent's, and closing them from here would break the parent's own session.
    The pid guard would catch this lazily anyway; clearing it here just means
    the child never holds a reference to a corpse.
    """
    global _cluster, _session, _owner_pid, _lock, _warm_thread

    _lock = threading.Lock()
    _cluster, _session, _owner_pid = None, None, None
    _warm_thread = None             # the parent's thread did not survive fork

    _start_warm_thread()


def start_warmup():
    """Warm this process now, and every forked child as it is created.

    Call once, from app.py at import. Idempotent in the sense that the at-fork
    hook is only ever registered once; calling it again starts another warm-up
    thread, which is harmless because connect_eagerly() reuses a live session.

    Returns True when the at-fork hook is in place. It is False on Windows,
    which has no fork() and therefore no os.register_at_fork -- the warm-up
    thread still runs, which is all a non-forking server needs.
    """
    global _fork_hook_registered

    if not _fork_hook_registered and hasattr(os, 'register_at_fork'):
        os.register_at_fork(after_in_child=_after_fork)
        _fork_hook_registered = True

    _start_warm_thread()
    return _fork_hook_registered
