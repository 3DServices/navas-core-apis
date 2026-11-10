# -*- coding: utf-8 -*-
"""Tests for require_signed_in and require_service_or_staff (endpoints/globals.py)

endpoints/globals.py imports Flask, psycopg2 and dateutil, so the two
decorators are compiled out of the module with ast and run against stubs,
as test_reply_scrub.py does.

What they guarantee: a notification route answers an anonymous caller with
401 whatever AUTH_GATE_MODE says, without looking a signed-in caller up a
second time.

Run:  python tests/test_signed_in_gate.py
"""

import ast
import io
import os
import sys
from functools import wraps
from types import SimpleNamespace

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE = os.path.join(ROOT, 'endpoints', 'globals.py')
WANTED = ('require_signed_in', 'require_service_or_staff')

RESULTS = []


def eq(name, got, want):
    RESULTS.append((name, got == want, 'got %r, want %r' % (got, want)))


class Stubs:
    """Stand-ins for flask.g and the two lookups the decorators fall back to."""

    def __init__(self):
        self.g = SimpleNamespace()
        self.lookups = 0          # times a fallback looked the caller up
        self.token_user = None    # who require_auth / require_staff would find

    def require_auth(self, f):
        @wraps(f)
        def wrapper(*a, **kw):
            self.lookups += 1
            if self.token_user is None:
                return 401
            return f(*a, **kw)
        return wrapper

    def require_staff(self, *perms):
        def decorator(f):
            @wraps(f)
            def wrapper(*a, **kw):
                self.lookups += 1
                if self.token_user is None:
                    return 401
                if self.token_user == 'customer':
                    return 403
                return f(*a, **kw)
            return wrapper
        return decorator


def load(stubs):
    with io.open(SOURCE, 'rb') as handle:
        text = handle.read().decode('utf-8').replace('\r\n', '\n')
    keep = [n for n in ast.parse(text).body
            if isinstance(n, ast.FunctionDef) and n.name in WANTED]
    missing = set(WANTED) - {n.name for n in keep}
    if missing:
        raise AssertionError('globals.py is missing: %s' % ', '.join(sorted(missing)))
    namespace = {'wraps': wraps, 'g': stubs.g,
                 'require_auth': stubs.require_auth,
                 'require_staff': stubs.require_staff}
    exec(compile(ast.Module(body=keep, type_ignores=[]), SOURCE, 'exec'), namespace)
    return namespace


def route():
    return 200


# ── require_signed_in: the customer-facing notification routes ─────────────

s = Stubs()
gate = load(s)['require_signed_in'](route)
eq('anonymous is refused (AUTH_GATE_MODE=report let it through)', gate(), 401)

s = Stubs()
s.g.current_user = {'account_uid': 'A1'}
gate = load(s)['require_signed_in'](route)
eq('signed in through access_guard: allowed', gate(), 200)
eq('... and not looked up a second time', s.lookups, 0)

s = Stubs()
s.g.service_call = True
eq('an internal caller with X-Service-Key: allowed',
   load(s)['require_signed_in'](route)(), 200)

s = Stubs()
s.token_user = 'customer'
gate = load(s)['require_signed_in'](route)
eq('no guard ran, but a valid token: require_auth lets it in', gate(), 200)
eq('... after one lookup', s.lookups, 1)

# ── require_service_or_staff: POST /notifications/log ──────────────────────

s = Stubs()
gate = load(s)['require_service_or_staff'](route)
eq('anonymous cannot write alerts', gate(), 401)

s = Stubs()
s.token_user = 'customer'
s.g.current_user = {'account_uid': 'C1'}
eq('a customer cannot write alerts', load(s)['require_service_or_staff'](route)(), 403)

s = Stubs()
s.token_user = 'staff'
eq('staff can', load(s)['require_service_or_staff'](route)(), 200)

s = Stubs()
s.g.service_call = True
eq('the service key can', load(s)['require_service_or_staff'](route)(), 200)


if __name__ == '__main__':
    failed = [r for r in RESULTS if not r[1]]
    for name, ok, detail in RESULTS:
        print('%s  %s%s' % ('PASS' if ok else 'FAIL', name,
                            '' if ok else '  -- ' + detail))
    print('\n%d passed, %d failed' % (len(RESULTS) - len(failed), len(failed)))
    sys.exit(1 if failed else 0)
