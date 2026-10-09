#!/usr/bin/env python3
"""
test_blacklist_cache.py -- the token revocation check is cached per request.
It must not become a way to use a revoked token.

Every route with a permission decorator decodes the token twice: once in the
access guard (access_guard.py:440) and again in the decorator (globals.py 434,
491, 525, 559). Each decode cost a round trip to a database 282 ms away --
measured at 1,148-1,270 ms per request on the dashboard routes, for an answer
that cannot change in the middle of a request.

Caching it is worth ~0.6 s on every decorated route. It is also, if done
carelessly, a way to let a revoked token through. The three tests that matter:

  * test_a_different_jti_is_not_served_from_another_jtis_answer
        The cache is keyed on the jti. A blanket "already checked this
        request" cache would hand a blacklisted token the clean answer from
        an earlier, different token. That is an authentication bypass.

  * test_the_cache_does_not_outlive_the_request
        It lives on flask.g. A process-wide cache would keep honouring a
        token for as long as the worker lived, which is the difference
        between "logout works" and "logout appears to work".

  * test_logging_out_drops_the_cached_answer
        blacklist_access_token() invalidates the jti it just revoked, so the
        token cannot pass again even in the request that revoked it.

No database is touched: the lookup is stubbed.
"""

import importlib.util
import os
import sys
import types
import unittest
from unittest import mock

sys.path.insert(0, '.')

from flask import Flask, g                                 # noqa: E402

# Loading by path, as the other store tests do -- endpoints/__init__.py pulls
# in every blueprint (and the Cassandra driver), which a bare checkout need not
# have. jwt_utils does `from . import db_pool`, so it has to be loaded AS part
# of the package: a bare path load raises "attempted relative import with no
# known parent package". So stand up a minimal `endpoints` package first and
# put the real db_pool in it.
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
jwt_utils = _load('endpoints.jwt_utils', 'jwt_utils.py')


class CacheTestCase(unittest.TestCase):

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

    def stub(self, answers):
        """Replace the database lookup with a dict, counting the calls."""
        calls = []

        def lookup(jti):
            calls.append(jti)
            return answers.get(str(jti), False)

        patch = mock.patch.object(jwt_utils, '_blacklist_lookup', lookup)
        patch.start()
        self.addCleanup(patch.stop)
        return calls


# ------------------------------------------------------- the three that matter

class TestItCannotLetARevokedTokenThrough(CacheTestCase):

    def test_a_different_jti_is_not_served_from_another_jtis_answer(self):
        """The whole point of keying on the jti."""
        calls = self.stub({'revoked-jti': True})

        self.assertFalse(jwt_utils._is_token_blacklisted('clean-jti'))
        self.assertTrue(jwt_utils._is_token_blacklisted('revoked-jti'),
                        'a revoked token must NOT inherit the clean answer '
                        'cached for a different token -- that is an '
                        'authentication bypass')
        self.assertEqual(calls, ['clean-jti', 'revoked-jti'],
                         'each distinct jti must be looked up once')

    def test_the_cache_does_not_outlive_the_request(self):
        """A revocation must take effect on the very next request."""
        answers = {}
        calls = self.stub(answers)

        self.assertFalse(jwt_utils._is_token_blacklisted('jti-1'))

        # the token is revoked between requests
        answers['jti-1'] = True

        self.ctx.pop()                       # request ends
        self.ctx = self.app.app_context()    # a new one begins
        self.ctx.push()

        self.assertTrue(jwt_utils._is_token_blacklisted('jti-1'),
                        'the cache must die with the request -- otherwise '
                        'logout only appears to work')
        self.assertEqual(calls, ['jti-1', 'jti-1'])

    def test_logging_out_drops_the_cached_answer(self):
        answers = {}
        self.stub(answers)

        self.assertFalse(jwt_utils._is_token_blacklisted('jti-9'))

        with mock.patch.object(jwt_utils.db_pool, 'connect',
                               side_effect=RuntimeError('no db in this test')):
            jwt_utils.blacklist_access_token('jti-9', 'acct', None)

        answers['jti-9'] = True
        self.assertTrue(jwt_utils._is_token_blacklisted('jti-9'),
                        'the jti just revoked must not keep its cached pass')


# ------------------------------------------------------- it actually caches

class TestItCaches(CacheTestCase):

    def test_the_same_jti_is_looked_up_once_per_request(self):
        calls = self.stub({})
        for _ in range(5):
            jwt_utils._is_token_blacklisted('jti-same')
        self.assertEqual(len(calls), 1,
                         'five checks of one token in one request must cost '
                         'one round trip, not five')

    def test_a_blacklisted_answer_is_cached_too(self):
        calls = self.stub({'bad': True})
        self.assertTrue(jwt_utils._is_token_blacklisted('bad'))
        self.assertTrue(jwt_utils._is_token_blacklisted('bad'))
        self.assertEqual(len(calls), 1)

    def test_jti_is_compared_as_a_string(self):
        calls = self.stub({'123': True})
        self.assertTrue(jwt_utils._is_token_blacklisted(123))
        self.assertTrue(jwt_utils._is_token_blacklisted('123'))
        self.assertEqual(len(calls), 1, 'int and str jti are the same key')


# ------------------------------------------------------- it stays safe

class TestItStaysSafe(CacheTestCase):

    def test_it_works_outside_a_request(self):
        """Scripts import this module too."""
        self.ctx.pop()
        calls = self.stub({'x': True})
        self.assertTrue(jwt_utils._is_token_blacklisted('x'))
        self.assertTrue(jwt_utils._is_token_blacklisted('x'))
        self.assertEqual(len(calls), 2,
                         'with no request to scope it to, every check is a '
                         'fresh lookup -- correct, if slower')
        self.ctx.push()

    def test_a_failing_lookup_still_fails_open(self):
        """Unchanged behaviour: a broken blacklist must not lock everyone out."""
        with mock.patch.object(jwt_utils.db_pool, 'connect',
                               side_effect=RuntimeError('db is down')):
            self.assertFalse(jwt_utils._blacklist_lookup('whatever'),
                             'the documented fail-open must survive')

    def test_decode_still_rejects_a_blacklisted_token(self):
        """End to end through decode_access_token, not just the helper."""
        self.stub({'the-jti': True})
        with mock.patch.object(jwt_utils.jwt, 'decode',
                               return_value={'sub': 'acct', 'jti': 'the-jti'}):
            self.assertIsNone(jwt_utils.decode_access_token('any-token'),
                              'a revoked token must still be refused')

    def test_decode_still_accepts_a_clean_token(self):
        self.stub({})
        with mock.patch.object(jwt_utils.jwt, 'decode',
                               return_value={'sub': 'acct', 'jti': 'fine'}):
            payload = jwt_utils.decode_access_token('any-token')
        self.assertEqual(payload.get('sub'), 'acct')


if __name__ == '__main__':
    unittest.main(verbosity=2)
