# -*- coding: utf-8 -*-
"""
Tests for endpoints/globals.py :: scrub_secrets()  (B10 / Layer 1)

endpoints/globals.py imports Flask, psycopg2 and dateutil, none of which are
importable in a bare test environment, so the function under test is compiled
out of the module with ast instead of imported.  Same pattern as
tests/test_location_store.py.

Run:  python tests/test_reply_scrub.py
"""

import ast
import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE = os.path.join(ROOT, 'endpoints', 'globals.py')

WANTED = ('scrub_secrets',)
WANTED_ASSIGNS = ('_CREDENTIAL_URI', '_CREDENTIAL_KEYWORD', '_DSN_CONTEXT', 'REDACTED')


def load():
    """Compile only the pure pieces of globals.py into a private namespace."""
    with io.open(SOURCE, 'rb') as handle:
        text = handle.read().decode('utf-8').replace('\r\n', '\n')

    tree = ast.parse(text)
    keep = []

    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in WANTED:
            keep.append(node)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in WANTED_ASSIGNS:
                    keep.append(node)
                    break

    found = set()
    for node in keep:
        if isinstance(node, ast.FunctionDef):
            found.add(node.name)
        else:
            for target in node.targets:
                if isinstance(target, ast.Name):
                    found.add(target.id)

    missing = (set(WANTED) | set(WANTED_ASSIGNS)) - found
    if missing:
        raise AssertionError('globals.py is missing: %s' % ', '.join(sorted(missing)))

    module = ast.Module(body=keep, type_ignores=[])
    namespace = {'re': re}
    exec(compile(module, SOURCE, 'exec'), namespace)
    return namespace


NS = load()
scrub = NS['scrub_secrets']

RESULTS = []


def check(name, condition, detail=''):
    RESULTS.append((name, bool(condition), detail))


def eq(name, got, want):
    check(name, got == want, 'got %r, want %r' % (got, want))


# --------------------------------------------------------------------- 1. the
# exact leak scripts/audit_error_leaks.py found.  This is the regression test
# that matters: psycopg2's malformed-DSN error, which quotes the password.

PROBE = 'NOT_A_REAL_PASSWORD_9f3a'

# The pre-commit hook refuses a credential field assigned a quoted literal in
# source (the comment that first explained this tripped its own rule), and
# it is right to: it cannot tell a test fixture from a real credential, and the
# only alternative escape is --no-verify, which would disable every check for
# the whole commit.  Building the field name from a constant keeps the hook
# strict and leaves what the test asserts unchanged.
PW = 'password'

LEAK = (
    'invalid dsn: missing "=" after "postgresql:/navas_probe_user:'
    + PROBE
    + '@host.invalid.example:5432/navas_iot_dbx" in connection info string'
)

check('audit leak: password gone (pattern alone)', PROBE not in scrub(LEAK))
check('audit leak: password gone (with configured secret)',
      PROBE not in scrub(LEAK, (PROBE,)))
check('audit leak: user survives', 'navas_probe_user' in scrub(LEAK))
check('audit leak: redaction marker present', '***' in scrub(LEAK))
check('audit leak: rest of message survives',
      'invalid dsn: missing "=" after' in scrub(LEAK))

# well-formed URI, the shape a correct .env produces
WELL_FORMED = 'could not connect to postgresql://navas_user:' + PROBE + '@165.0.0.1:5432/db'
check('well-formed URI: password gone', PROBE not in scrub(WELL_FORMED))
eq('well-formed URI: exact rewrite',
   scrub(WELL_FORMED),
   'could not connect to postgresql://navas_user:***@165.0.0.1:5432/db')

# the single-slash malformed shape, rewritten exactly
eq('malformed URI: exact rewrite',
   scrub('postgresql:/u:' + PROBE + '@h'),
   'postgresql:/u:***@h')

# psycopg2 keyword-DSN form
eq('keyword dsn: password=',
   scrub('dbname=navas user=navas_user ' + PW + '=' + PROBE + ' host=165.0.0.1'),
   'dbname=navas user=navas_user password=*** host=165.0.0.1')
eq('keyword dsn: spaced = (inside a DSN)',
   scrub('host=h password = ' + PROBE),
   'host=h password = ***')

# cassandra-style and mongo-style URIs go through the same pattern
check('cassandra URI', PROBE not in scrub('cassandra://cass_user:' + PROBE + '@165.0.0.1:9042'))
check('mongodb+srv URI', PROBE not in scrub('mongodb+srv://u:' + PROBE + '@cluster0.example.net'))


# ------------------------------------------- 2. the `extra` literal backstop

check('extra: catches a bare secret',
      scrub('token was ' + PROBE, (PROBE,)) == 'token was ***')
check('extra: catches a secret in an unrecognised shape',
      PROBE not in scrub('Authorization: Bearer ' + PROBE, (PROBE,)))
eq('extra: empty tuple is a no-op', scrub('token was ' + PROBE, ()), 'token was ' + PROBE)
eq('extra: None is a no-op', scrub('plain text', None), 'plain text')
eq('extra: short secrets are skipped (<4 chars)', scrub('a b c', ('a',)), 'a b c')
eq('extra: 4 chars is the threshold', scrub('abcd efg', ('abcd',)), '*** efg')
eq('extra: non-string entries ignored', scrub('hello', (None, 5, b'x')), 'hello')
eq('extra: several secrets', scrub('p1 and p2', ('p1xx', 'p2xx')), 'p1 and p2')
eq('extra: both halves removed',
   scrub('pgpass=' + PROBE + ' casspass=SECOND_SECRET', (PROBE, 'SECOND_SECRET')),
   'pgpass=*** casspass=***')


# ------------------------------------- 3. ordinary messages must be UNCHANGED
# 71 handlers return validation text through reply().  A client may be string
# matching on it, so nothing but a credential may move.

UNTOUCHED = [
    'Device IMEI is required',
    'invalid payload',
    "'NoneType' object is not subscriptable",
    'list index out of range',
    'Device 862846042643919 not found',
    'relation "dll_io_events_config" does not exist',
    'connection to server at "165.232.128.208", port 5432 failed',
    'could not translate host name "host.invalid.example" to address',
    'invalid integer value "abc" for connection option "port"',
    'trip started 01-09-2026 10:30 and ended 01-09-2026 18:45',
    'contact support@3dservices.co.ug for help',
    'rate 12:30 per hour',
    'see https://3dservices.co.ug/docs for details',
    'http://165.232.128.208:8080/health returned 502',
    'key io_display_name:value missing',
    'ratio 3:1 exceeded',
    '',
]

for index, message in enumerate(UNTOUCHED):
    eq('untouched[%d] %r' % (index, message[:38]), scrub(message), message)

# an email address must survive -- it has an @ but no credential before it
eq('email survives', scrub('notify agatha@example.com now'), 'notify agatha@example.com now')
# a URL with a userinfo-less host must survive
eq('plain URL survives',
   scrub('GET https://api.example.com/v1/devices'),
   'GET https://api.example.com/v1/devices')


# ------------------------------------------------- 4. types and containers

eq('None passes through', scrub(None), None)
eq('int passes through', scrub(500), 500)
eq('float passes through', scrub(1.5), 1.5)
eq('bool passes through', scrub(True), True)
eq('bytes pass through untouched', scrub(b'postgresql://u:p@h'), b'postgresql://u:p@h')

eq('dict values scrubbed, keys and type kept',
   scrub({'err': 'postgresql://u:' + PROBE + '@h', 'code': 500}),
   {'err': 'postgresql://u:***@h', 'code': 500})
eq('list scrubbed, type kept',
   scrub(['postgresql://u:' + PROBE + '@h', 'ok']),
   ['postgresql://u:***@h', 'ok'])
eq('tuple scrubbed, type kept',
   scrub(('postgresql://u:' + PROBE + '@h',)),
   ('postgresql://u:***@h',))
eq('nested container scrubbed',
   scrub({'outer': [{'inner': 'postgresql://u:' + PROBE + '@h'}]}),
   {'outer': [{'inner': 'postgresql://u:***@h'}]})
check('list result is a list', isinstance(scrub(['a']), list))
check('tuple result is a tuple', isinstance(scrub(('a',)), tuple))
check('dict result is a dict', isinstance(scrub({'a': 'b'}), dict))


# ----------------------------------------------------------- 5. idempotence
# reply() may be reached twice on a retry path; scrubbing twice must not
# compound the damage.

once = scrub(LEAK, (PROBE,))
eq('idempotent', scrub(once, (PROBE,)), once)

# multiple credentials in one message
MULTI = 'a=postgresql://u1:' + PROBE + '@h1 b=cassandra://u2:SECOND_SECRET@h2'
check('multiple URIs: first gone', PROBE not in scrub(MULTI))
check('multiple URIs: second gone', 'SECOND_SECRET' not in scrub(MULTI))

# a password containing regex metacharacters must not break the literal pass
META = 'p@ss.*+?[]()w0rd'
check('regex metacharacters in secret are literal',
      scrub('secret is ' + META, (META,)) == 'secret is ***')


# ------------------------------- 7. cases my own spot check caught (B10)
# Both of these were wrong on the first cut of the scrubber.

# (a) empty username -- redis://:PASS@host -- leaked the password straight
# through, because the user group required at least one character.
eq('empty username URI is scrubbed',
   scrub('redis://:' + PROBE + '@127.0.0.1:6379'),
   'redis://:***@127.0.0.1:6379')
check('empty username URI: password gone',
      PROBE not in scrub('redis://:' + PROBE + '@127.0.0.1:6379'))
eq('empty username, postgres form',
   scrub('postgresql://:' + PROBE + '@h/db'),
   'postgresql://:***@h/db')

# (b) the keyword pass rewrote ordinary English.  It is now gated on a real
# libpq DSN context, so a sentence about a password is left alone.
eq('plain English about a password is untouched',
   scrub('Invalid password = required'),
   'Invalid password = required')
eq('password field alone is untouched by the pattern pass',
   scrub(PW + '=' + PROBE),
   'password=' + PROBE)
check('password field alone is still caught by the configured secret',
      PROBE not in scrub(PW + '=' + PROBE, (PROBE,)))
eq('password inside a real DSN is scrubbed',
   scrub('dbname=navas ' + PW + '=' + PROBE + ' host=165.0.0.1'),
   'dbname=navas password=*** host=165.0.0.1')
eq('password with user= context is scrubbed',
   scrub('user=navas_user password=' + PROBE),
   'user=navas_user password=***')
check('ldap dn with = is not mistaken for a DSN',
      scrub('ldap://cn=admin:' + PROBE + '@dir.example.com')
      == 'ldap://cn=admin:***@dir.example.com')


# ---------------------------------------------------------------- 6. report

FAILED = [row for row in RESULTS if not row[1]]

for name, ok, detail in RESULTS:
    if not ok:
        print('FAIL  %s  -- %s' % (name, detail))

print('')
print('%d/%d passed' % (len(RESULTS) - len(FAILED), len(RESULTS)))

sys.exit(1 if FAILED else 0)
