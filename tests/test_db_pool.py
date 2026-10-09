#!/usr/bin/env python3
"""
test_db_pool.py -- the pool must be invisible to callers and impossible to
drain.

Two of these tests are the reason the module exists at all; the rest are
scaffolding.

  * test_teardown_reclaims_a_connection_nobody_closed
        310 call sites in this codebase use `with conn:` and never close.
        Hand those a pooled connection and they leak pool slots -- nothing
        collects those, so the pool empties and every later request blocks
        forever. The teardown hook is the only thing standing between a slow
        dashboard and a hung application. If this test ever goes red, do not
        deploy.

  * test_warm_size_is_minconn_not_maxconn
        psycopg2's AbstractConnectionPool._putconn keeps a returned
        connection only `if len(self._pool) < self.minconn`, and CLOSES it
        otherwise. So minconn is the pool size and maxconn is only a ceiling
        on concurrent checkouts. Build it the tempting way -- minconn=1,
        maxconn=20 -- and the pool looks installed and does nothing: every
        connection past the first is discarded on return and the next
        request pays 2,027 ms again. This pins the construction.

No database is touched. The pool and connections are fakes, so these run
anywhere, including where 165.232.128.208 is unreachable.
"""

import importlib.util
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, '.')

import psycopg2                                            # noqa: E402
import psycopg2.pool                                       # noqa: E402
from flask import Flask                                    # noqa: E402

# Load the module from its path rather than `from endpoints import db_pool`:
# endpoints/__init__.py imports every blueprint, which pulls in the Cassandra
# driver, and a bare checkout need not have it. This is the convention the
# other store tests here already use (test_io_events_store, test_location_store).
_PATH = os.path.join(os.path.dirname(__file__), '..', 'endpoints',
                     'db_pool.py')
_spec = importlib.util.spec_from_file_location('db_pool', _PATH)
db_pool = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(db_pool)


# --------------------------------------------------------------- fakes

class FakeConnection:
    """Enough of a psycopg2 connection to tell pooling from closing."""

    def __init__(self):
        self.closed = 0
        self.rollbacks = 0
        self.commits = 0
        self.entered = 0
        self.exited = 0
        self._autocommit = False
        self.autocommit_history = []

    @property
    def autocommit(self):
        return self._autocommit

    @autocommit.setter
    def autocommit(self, value):
        self._autocommit = value
        self.autocommit_history.append(value)

    def close(self):
        self.closed = 1

    def rollback(self):
        self.rollbacks += 1

    def commit(self):
        self.commits += 1

    def cursor(self):
        return 'a-cursor'

    def __enter__(self):
        self.entered += 1
        return self

    def __exit__(self, exc_type, exc_value, tb):
        self.exited += 1
        if exc_type is None:
            self.commit()
        else:
            self.rollback()
        return False


class FakePool:
    """A pool that records what it is handed back."""

    def __init__(self, connections=None, fail_with=None):
        # `connections or [default]` would be wrong: an empty list is falsy,
        # so FakePool([]) -- the exhausted-pool case -- would silently come
        # back with one connection and the fallback test would pass for the
        # wrong reason. It did, until this line was fixed.
        if connections is None:
            connections = [FakeConnection()]
        self.available = list(connections)
        self.returned = []
        self.fail_with = fail_with

    def getconn(self):
        if self.fail_with is not None:
            raise self.fail_with
        if not self.available:
            raise psycopg2.pool.PoolError('connection pool exhausted')
        return self.available.pop()

    def putconn(self, conn):
        self.returned.append(conn)


class PoolTestCase(unittest.TestCase):
    """Installs a fake pool and an app context, and cleans both up."""

    def setUp(self):
        self.app = Flask(__name__)
        self.app.config['db_link'] = 'postgresql://unused/for-tests'
        self.ctx = self.app.app_context()
        self.ctx.push()
        self._saved = (db_pool._pool, db_pool._pool_state)

    def tearDown(self):
        db_pool._pool, db_pool._pool_state = self._saved
        try:
            self.ctx.pop()
        except Exception:                                  # noqa: BLE001
            pass

    def install(self, pool):
        db_pool._pool = pool
        db_pool._pool_state = 'ready'
        return pool


# --------------------------------------------------------------- the two that matter

class TestTheWholePoint(PoolTestCase):

    def test_teardown_reclaims_a_connection_nobody_closed(self):
        """The 310-call-site case. Nobody closes; teardown must."""
        conn = FakeConnection()
        pool = self.install(FakePool([conn]))

        handed = db_pool.connect()
        with handed:                      # commits, does NOT close
            handed.cursor()

        self.assertEqual(pool.returned, [],
                         'nothing should be back in the pool yet')
        self.assertEqual(conn.closed, 0, 'the socket must stay open')

        db_pool.release_all()             # what teardown_appcontext calls

        self.assertEqual(pool.returned, [conn],
                         'teardown must return the connection to the pool')
        self.assertEqual(conn.closed, 0,
                         'it must be pooled, not closed')

    def test_warm_size_is_minconn_not_maxconn(self):
        """minconn is the pool size. maxconn alone keeps nothing warm."""
        seen = {}

        class Recorder:
            def __init__(self, minconn, maxconn, dsn):
                seen['minconn'] = minconn
                seen['maxconn'] = maxconn

        with mock.patch.object(psycopg2.pool, 'ThreadedConnectionPool',
                               Recorder):
            db_pool._build('postgresql://unused/for-tests')

        self.assertEqual(seen['minconn'], db_pool._POOL_SIZE,
                         'minconn must be the number kept warm -- psycopg2 '
                         'closes anything returned beyond it')
        self.assertGreaterEqual(seen['maxconn'], seen['minconn'])
        self.assertGreater(seen['minconn'], 1,
                           'a minconn of 1 keeps one connection warm and '
                           'discards every other, which is a pool in name '
                           'only')


# --------------------------------------------------------------- behaviour

class TestProxyBehaviour(PoolTestCase):

    def test_close_returns_to_pool_and_does_not_shut_the_socket(self):
        conn = FakeConnection()
        pool = self.install(FakePool([conn]))
        handed = db_pool.connect()
        handed.close()
        self.assertEqual(pool.returned, [conn])
        self.assertEqual(conn.closed, 0)

    def test_close_is_idempotent(self):
        conn = FakeConnection()
        pool = self.install(FakePool([conn]))
        handed = db_pool.connect()
        handed.close()
        handed.close()
        handed.close()
        self.assertEqual(len(pool.returned), 1,
                         'a connection must not be returned twice -- that '
                         'hands the same socket to two requests')

    def test_teardown_after_an_explicit_close_does_not_double_return(self):
        conn = FakeConnection()
        pool = self.install(FakePool([conn]))
        handed = db_pool.connect()
        handed.close()
        db_pool.release_all()
        self.assertEqual(len(pool.returned), 1)

    def test_rollback_happens_before_the_connection_is_reused(self):
        """A failed transaction must not travel to the next request."""
        conn = FakeConnection()
        self.install(FakePool([conn]))
        handed = db_pool.connect()
        handed.close()
        self.assertGreaterEqual(conn.rollbacks, 1,
                                'release must roll back: a connection in a '
                                'failed transaction gives the next request '
                                'wrong answers, not errors')

    def test_with_block_still_commits(self):
        conn = FakeConnection()
        self.install(FakePool([conn]))
        handed = db_pool.connect()
        with handed:
            pass
        self.assertEqual(conn.entered, 1)
        self.assertEqual(conn.commits, 1, '`with conn:` must still commit')

    def test_with_block_still_rolls_back_on_error(self):
        conn = FakeConnection()
        self.install(FakePool([conn]))
        handed = db_pool.connect()
        with self.assertRaises(ValueError):
            with handed:
                raise ValueError('boom')
        self.assertGreaterEqual(conn.rollbacks, 1)

    def test_attributes_and_methods_delegate(self):
        conn = FakeConnection()
        self.install(FakePool([conn]))
        handed = db_pool.connect()
        self.assertEqual(handed.cursor(), 'a-cursor')
        self.assertEqual(handed.closed, 0)
        handed.autocommit = True
        self.assertTrue(conn.autocommit,
                        'setting an attribute must reach the real connection')

    def test_use_after_release_is_an_honest_error(self):
        conn = FakeConnection()
        self.install(FakePool([conn]))
        handed = db_pool.connect()
        handed.close()
        self.assertTrue(handed.closed, 'a released proxy reports closed')
        with self.assertRaises(psycopg2.InterfaceError):
            handed.cursor()


# --------------------------------------------------------------- fallbacks

class TestNeverWorseThanBefore(PoolTestCase):
    """The pool may speed things up or do nothing. It may not break a request."""

    def test_exhausted_pool_falls_back_to_a_direct_connection(self):
        self.install(FakePool([]))          # nothing available
        sentinel = FakeConnection()
        with mock.patch.object(psycopg2, 'connect', return_value=sentinel) \
                as direct:
            handed = db_pool.connect()
        direct.assert_called_once()
        self.assertIs(handed, sentinel,
                      'an exhausted pool must serve a direct connection, '
                      'not refuse the request')

    def test_a_pool_that_raises_falls_back(self):
        self.install(FakePool(fail_with=RuntimeError('pool is unwell')))
        sentinel = FakeConnection()
        with mock.patch.object(psycopg2, 'connect', return_value=sentinel):
            handed = db_pool.connect()
        self.assertIs(handed, sentinel)

    def test_before_the_pool_is_built_connections_are_direct(self):
        db_pool._pool, db_pool._pool_state = None, 'building'
        sentinel = FakeConnection()
        with mock.patch.object(psycopg2, 'connect', return_value=sentinel):
            handed = db_pool.connect()
        self.assertIs(handed, sentinel,
                      'startup must not wait for a warm pool')

    def test_a_failed_build_leaves_the_app_working(self):
        with mock.patch.object(psycopg2.pool, 'ThreadedConnectionPool',
                               side_effect=RuntimeError('no route to host')):
            db_pool._build('postgresql://unused/for-tests')
        self.assertEqual(db_pool._pool_state, 'failed')
        sentinel = FakeConnection()
        with mock.patch.object(psycopg2, 'connect', return_value=sentinel):
            handed = db_pool.connect()
        self.assertIs(handed, sentinel)

    def test_release_all_is_safe_with_nothing_checked_out(self):
        self.install(FakePool())
        db_pool.release_all()               # must not raise

    def test_release_all_outside_an_app_context_is_safe(self):
        self.ctx.pop()
        db_pool.release_all()               # must not raise
        self.ctx.push()

    def test_one_bad_release_does_not_strand_the_others(self):
        good_a, good_b = FakeConnection(), FakeConnection()
        bad = FakeConnection()
        pool = self.install(FakePool([good_b, bad, good_a]))
        db_pool.connect()
        middle = db_pool.connect()
        db_pool.connect()
        # make the middle one explode on release
        object.__setattr__(middle, '_owner', FakePool(fail_with=None))
        middle._owner.putconn = mock.Mock(side_effect=RuntimeError('nope'))
        db_pool.release_all()
        self.assertEqual(len(pool.returned), 2,
                         'the other two must still be reclaimed')


class TestStats(PoolTestCase):

    def test_stats_reports_state_without_a_pool(self):
        db_pool._pool, db_pool._pool_state = None, 'not started'
        self.assertEqual(db_pool.stats()['state'], 'not started')

    def test_stats_counts_pooled_and_direct(self):
        before = db_pool.stats()
        conn = FakeConnection()
        self.install(FakePool([conn]))
        db_pool.connect()
        after = db_pool.stats()
        self.assertEqual(after['pooled_connects'],
                         before['pooled_connects'] + 1)


# --------------------------------------------------------------- read-only

class TestReadOnlyConnections(PoolTestCase):
    """readonly=True removes the BEGIN -- worth one round trip, 283 ms here.

    test_a_readonly_connection_is_reset_before_going_back is the one that
    matters. A connection returned with autocommit still on would silently
    strip transactions from whatever code picks it up next: a write path
    would lose its atomicity with no error and no sign at all. That is the
    single hazard this feature introduces, and it is the reason the reset
    happens first in close(), before anything else can fail and skip it.
    """

    def test_readonly_turns_autocommit_on(self):
        conn = FakeConnection()
        self.install(FakePool([conn]))
        db_pool.connect(readonly=True)
        self.assertTrue(conn.autocommit,
                        'no autocommit means psycopg2 still sends BEGIN, '
                        'which is the round trip this exists to avoid')

    def test_the_default_is_still_transactional(self):
        conn = FakeConnection()
        self.install(FakePool([conn]))
        db_pool.connect()
        self.assertFalse(conn.autocommit,
                         'every existing caller must keep its transaction')

    def test_a_readonly_connection_is_reset_before_going_back(self):
        conn = FakeConnection()
        pool = self.install(FakePool([conn]))
        handed = db_pool.connect(readonly=True)
        self.assertTrue(conn.autocommit)

        handed.close()

        self.assertFalse(conn.autocommit,
                         'a connection returned with autocommit ON would '
                         'silently remove transactions from the next caller')
        self.assertEqual(pool.returned, [conn])
        self.assertEqual(conn.autocommit_history, [True, False],
                         'on for the read, off again before it is reused')

    def test_teardown_also_resets_it(self):
        """The 310 call sites that never close reach the pool this way."""
        conn = FakeConnection()
        self.install(FakePool([conn]))
        db_pool.connect(readonly=True)
        db_pool.release_all()
        self.assertFalse(conn.autocommit,
                         'the teardown path must reset it too, not just '
                         'an explicit close()')

    def test_a_normal_connection_is_not_touched(self):
        conn = FakeConnection()
        self.install(FakePool([conn]))
        db_pool.connect().close()
        self.assertEqual(conn.autocommit_history, [],
                         'a transactional checkout must not fiddle with the '
                         'flag at all')

    def test_the_direct_fallback_honours_readonly_too(self):
        """An exhausted pool must not quietly give back a transactional one."""
        self.install(FakePool([]))
        sentinel = FakeConnection()
        with mock.patch.object(psycopg2, 'connect', return_value=sentinel):
            db_pool.connect(readonly=True)
        self.assertTrue(sentinel.autocommit)

    def test_with_block_opens_NO_transaction_on_a_readonly_connection(self):
        """The whole fix. Measured: `with conn:` costs a round trip even with
        autocommit on (614 ms vs 307 ms), so on a read-only connection it must
        not reach the real connection at all. Without this, readonly=True buys
        nothing at the 310 call sites that use the idiom -- which is what the
        first attempt did, improving exactly one."""
        conn = FakeConnection()
        self.install(FakePool([conn]))
        handed = db_pool.connect(readonly=True)
        with handed:
            handed.cursor()
        self.assertEqual(conn.entered, 0,
                         'a read-only `with conn:` must NOT open a '
                         'transaction -- that is the entire round trip this '
                         'change exists to save')
        self.assertEqual(conn.commits, 0, 'nothing was opened to commit')
        handed.close()
        self.assertEqual(conn.closed, 0)

    def test_a_transactional_with_block_is_untouched(self):
        """Every existing caller keeps its transaction, unchanged."""
        conn = FakeConnection()
        self.install(FakePool([conn]))
        handed = db_pool.connect()
        with handed:
            handed.cursor()
        self.assertEqual(conn.entered, 1)
        self.assertEqual(conn.commits, 1,
                         'a normal connection must still commit on exit')

    def test_an_error_inside_a_readonly_with_block_still_propagates(self):
        """Suppressing the exception would be far worse than the round trip."""
        conn = FakeConnection()
        self.install(FakePool([conn]))
        handed = db_pool.connect(readonly=True)
        with self.assertRaises(ValueError):
            with handed:
                raise ValueError('boom')
        self.assertEqual(conn.rollbacks, 0,
                         'there was no transaction to roll back')

    def test_a_transactional_error_still_rolls_back(self):
        conn = FakeConnection()
        self.install(FakePool([conn]))
        handed = db_pool.connect()
        with self.assertRaises(ValueError):
            with handed:
                raise ValueError('boom')
        self.assertGreaterEqual(conn.rollbacks, 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
