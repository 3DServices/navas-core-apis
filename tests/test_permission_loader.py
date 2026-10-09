#!/usr/bin/env python3
"""
test_permission_loader.py -- the access guard's lookup, collapsed from three
round trips to one, must return exactly what it returned before.

This is the function that decides what every authenticated caller may do. The
three outcomes it has always had are pinned here:

    no active account row   -> (None, None, None, [])
    role not found          -> (clearance, type, root, [])
    role found              -> (clearance, type, root, [names...])

These tests drive a fake cursor, so they pin the SHAPE of the contract -- that
one empty result means "no such account" and a result with NULL permission
names means "no permissions", which are different answers that now arrive in
the same query. What they cannot pin is whether the SQL itself selects the
same rows as the three statements it replaces; that is a question about the
data, and scripts/verify_permission_parity.py answers it against every real
account.

Read the SQL's own comments for the two traps it avoids: the role-name-before-
role-uid precedence (a plain OR would union two roles' permissions and grant
more than before), and ORDER BY <bool> DESC being NULLS FIRST in Postgres.
"""

import importlib.util
import os
import sys
import types
import unittest
from unittest import mock

sys.path.insert(0, '.')

from flask import Flask                                    # noqa: E402

_HERE = os.path.dirname(__file__)
_ENDPOINTS = os.path.join(_HERE, '..', 'endpoints')


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(
        name, os.path.join(_ENDPOINTS, filename))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


if 'endpoints' not in sys.modules:
    _pkg = types.ModuleType('endpoints')
    _pkg.__path__ = [_ENDPOINTS]
    sys.modules['endpoints'] = _pkg

_load('endpoints.db_pool', 'db_pool.py')
_load('endpoints.jwt_utils', 'jwt_utils.py')
globals_mod = _load('endpoints.globals', 'globals.py')


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows
        self.statements = []

    def execute(self, sql, params=None):
        self.statements.append((sql, params))

    def fetchall(self):
        return list(self.rows)

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeConnection:
    def __init__(self, rows):
        self._cursor = FakeCursor(rows)
        self.closed = 0

    def cursor(self):
        return self._cursor

    def close(self):
        self.closed = 1

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class LoaderTestCase(unittest.TestCase):

    def setUp(self):
        self.app = Flask(__name__)
        self.app.config['db_link'] = 'postgresql://unused/for-tests'
        self.ctx = self.app.app_context()
        self.ctx.push()

    def tearDown(self):
        try:
            self.ctx.pop()
        except Exception:                                  # noqa: BLE001
            pass

    def load(self, rows, account='acct-1'):
        conn = FakeConnection(rows)
        with mock.patch.object(globals_mod.db_pool, 'connect',
                               return_value=conn):
            result = globals_mod._load_user_permissions(account)
        return result, conn


class TestTheThreeOutcomes(LoaderTestCase):

    def test_no_active_account_row(self):
        """Empty result means no such active account -- all None."""
        result, _ = self.load([])
        self.assertEqual(result, (None, None, None, []))

    def test_role_not_found_keeps_the_identity_but_grants_nothing(self):
        """The LEFT JOINs give one row with a NULL permission name."""
        result, _ = self.load([('admin', 'client', 'root-1', None)])
        self.assertEqual(result, ('admin', 'client', 'root-1', []),
                         'a missing role must keep the identity and return '
                         'no permissions -- not treat the account as absent')

    def test_role_found_returns_its_permissions(self):
        result, _ = self.load([
            ('admin', 'client', 'root-1', 'devices.view'),
            ('admin', 'client', 'root-1', 'devices.create'),
            ('admin', 'client', 'root-1', 'tokens.view_balance'),
        ])
        self.assertEqual(result[:3], ('admin', 'client', 'root-1'))
        self.assertEqual(sorted(result[3]),
                         ['devices.create', 'devices.view',
                          'tokens.view_balance'])

    def test_a_null_permission_among_real_ones_is_dropped(self):
        """Defensive: a NULL must never arrive in the permission list."""
        result, _ = self.load([
            ('admin', 'client', 'root-1', 'devices.view'),
            ('admin', 'client', 'root-1', None),
        ])
        self.assertEqual(result[3], ['devices.view'])
        self.assertNotIn(None, result[3],
                         'None in a permission list would compare oddly '
                         'against every permission check')


class TestItIsOneRoundTrip(LoaderTestCase):

    def test_exactly_one_statement_is_executed(self):
        """The whole point: three round trips became one."""
        _, conn = self.load([('admin', 'client', 'root-1', 'devices.view')])
        self.assertEqual(len(conn._cursor.statements), 1,
                         'the collapse is the change -- more than one '
                         'statement means it did not happen')

    def test_the_account_uid_is_passed_as_a_string(self):
        _, conn = self.load([], account=12345)
        _, params = conn._cursor.statements[0]
        self.assertEqual(params, {'uid': '12345'})

    def test_the_connection_is_returned(self):
        _, conn = self.load([])
        self.assertEqual(conn.closed, 1,
                         'the pooled connection must go back')


class TestItStaysSafe(LoaderTestCase):
    """Error handling must be IDENTICAL to the three-query version.

    The original is inconsistent here, and this change deliberately does not
    fix that: a failure while QUERYING is swallowed and returns the no-access
    tuple, which the guard reports as "inactive account" (a 401), while a
    failure while CONNECTING propagates and becomes a 500. So a database
    outage tells the caller two different stories depending on exactly when it
    happens -- and "inactive account" is a misleading thing to tell someone
    whose account is fine.

    That is worth fixing, but not in a change whose claim is "same answers,
    one round trip instead of three". Pinned here so the inconsistency is
    recorded rather than rediscovered, and so neither behaviour drifts by
    accident.
    """

    def test_a_failure_while_querying_returns_the_no_access_tuple(self):
        conn = FakeConnection([])

        def boom(*a, **kw):
            raise RuntimeError('connection reset mid-query')

        conn._cursor.execute = boom
        with mock.patch.object(globals_mod.db_pool, 'connect',
                               return_value=conn):
            result = globals_mod._load_user_permissions('acct-1')
        self.assertEqual(result, (None, None, None, []))
        self.assertEqual(conn.closed, 1,
                         'the connection must go back even on the error path')

    def test_a_failure_while_connecting_still_propagates(self):
        """As before. Documented above, not silently changed."""
        with mock.patch.object(globals_mod.db_pool, 'connect',
                               side_effect=RuntimeError('db is down')):
            with self.assertRaises(RuntimeError):
                globals_mod._load_user_permissions('acct-1')


class TestTheSqlItself(unittest.TestCase):
    """Cheap checks on the statement that unit tests cannot otherwise reach."""

    def test_precedence_between_role_name_and_role_uid_is_explicit(self):
        sql = globals_mod._PERMISSIONS_SQL
        self.assertIn('ORDER BY COALESCE(r.role_name = a.account_clearance',
                      sql,
                      'without the ordering a name match and a uid match are '
                      'interchangeable, which can union two roles')
        self.assertIn('LIMIT 1', sql, 'exactly one role, as before')

    def test_the_null_ordering_trap_is_handled(self):
        """ORDER BY <bool> DESC is NULLS FIRST in Postgres."""
        self.assertIn('COALESCE(', globals_mod._PERMISSIONS_SQL)

    def test_deleted_roles_and_permissions_are_still_excluded(self):
        sql = globals_mod._PERMISSIONS_SQL
        self.assertEqual(sql.count('is_deleted'), 4,
                         'both the role and the permission filters must '
                         'survive, each as a FALSE-or-NULL pair')

    def test_only_active_accounts(self):
        self.assertIn("access_status = 'active'", globals_mod._PERMISSIONS_SQL)


if __name__ == '__main__':
    unittest.main(verbosity=2)
