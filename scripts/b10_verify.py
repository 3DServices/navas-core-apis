#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
B10 end-to-end verification -- run this in the venv that has Flask.

tests/test_reply_scrub.py proves scrub_secrets() itself.  This proves the
WIRING: that reply() actually calls it, that _configured_secrets() really
pulls the password out of current_app.config['db_link'], and that the
password cannot reach a caller even when db_link is the malformed shape that
made psycopg2 quote it in the first place.

No database is contacted.  Nothing is written.

    python scripts/b10_verify.py
"""

import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask                      # noqa: E402
from endpoints.globals import reply, scrub_secrets, _configured_secrets   # noqa: E402

PROBE = 'NOT_A_REAL_PASSWORD_9f3a'

RESULTS = []


def check(name, ok, detail=''):
    RESULTS.append((name, bool(ok), detail))


def body_of(response):
    """The JSON payload reply() produced, as text."""
    payload, _code = response
    return payload.get_data(as_text=True)


def fields_of(response):
    """The payload PARSED.

    Substring-matching the serialised body is wrong: jsonify escapes the
    double quotes in a message like  connection to server at "165.x.x.x"
    so the raw string is not a substring of the response text.  That made
    this script report a FAIL on a message the scrubber had not touched.
    Compare the decoded field instead.
    """
    return json.loads(body_of(response))


def code_of(response):
    _payload, code = response
    return code


# the two db_link shapes that matter: the well-formed one production uses, and
# the malformed one that makes psycopg2 echo the password
LINKS = {
    'well-formed URI':
        'postgresql://navas_user:' + PROBE + '@165.232.128.208:5432/navas_iot_dbx',
    'malformed URI (the leak case)':
        'postgresql:/navas_user:' + PROBE + '@165.232.128.208:5432/navas_iot_dbx',
    'keyword DSN':
        'dbname=navas_iot_dbx user=navas_user password=' + PROBE
        + ' host=165.232.128.208 port=5432',
}

# the exact text psycopg2 produced in scripts/audit_error_leaks.py
LEAK = (
    'invalid dsn: missing "=" after "postgresql:/navas_user:'
    + PROBE
    + '@165.232.128.208:5432/navas_iot_dbx" in connection info string'
)

for label, link in LINKS.items():
    app = Flask(__name__)
    app.config['db_link'] = link

    with app.app_context():
        secrets = _configured_secrets()
        check('%s: password extracted from db_link' % label, PROBE in secrets,
              'got %r' % (secrets,))

        out = fields_of(reply('error', 500, LEAK, ''))['message']
        check('%s: password absent from the response' % label, PROBE not in out,
              out[:200])
        check('%s: response still says what failed' % label, 'invalid dsn' in out)

        # a secret in a shape the patterns do not recognise -- the configured
        # literal is the backstop
        odd = fields_of(reply('error', 500, 'upstream said ' + PROBE, ''))['message']
        check('%s: bare secret in an odd shape is removed' % label,
              PROBE not in odd, odd[:200])

# ordinary responses must be byte-identical to before the patch
app = Flask(__name__)
app.config['db_link'] = LINKS['well-formed URI']

with app.app_context():
    for message in ['Device IMEI is required',
                    'invalid payload',
                    'Trip history is temporarily unavailable, please retry',
                    'Position data is temporarily unavailable, please retry',
                    "'NoneType' object is not subscriptable",
                    'connection to server at "165.232.128.208", port 5432 failed']:
        got = fields_of(reply('error', 400, message, ''))['message']
        check('unchanged: %r' % message[:40], got == message,
              'got %r, want %r' % (got, message))

    ok = reply('success', 200, 'Data found', {'trips': 3, 'note': 'a "quoted" value'})
    fields = fields_of(ok)
    check('success: status field', fields['status'] == 'success', str(fields))
    check('success: message field', fields['message'] == 'Data found', str(fields))
    check('success: data passes through untouched',
          fields['data'] == {'trips': 3, 'note': 'a "quoted" value'}, str(fields))
    check('status code passes through', code_of(ok) == 200, str(code_of(ok)))

# no app context at all: must not raise
check('no app context: _configured_secrets() returns ()', _configured_secrets() == ())
check('no app context: scrub_secrets() still works',
      scrub_secrets('postgresql://u:' + PROBE + '@h') == 'postgresql://u:***@h')

# the 503 guard is in trips_history, not somewhere else in data.py
source = io.open(
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__, encoding='utf-8'))),
                 'endpoints', 'data.py'),
    'rb').read().decode('utf-8').replace('\r\n', '\n')

import ast   # noqa: E402

tree = ast.parse(source)
guard_sites = []
for node in ast.walk(tree):
    if isinstance(node, ast.FunctionDef):
        lines = source.split('\n')[node.lineno - 1:node.end_lineno]
        if 'trips_history: database connection failed' in '\n'.join(lines):
            guard_sites.append(node.name)

check('503 guard lives only in trips_history()', guard_sites == ['trips_history'],
      str(guard_sites))

FAILED = [row for row in RESULTS if not row[1]]

for name, ok, detail in RESULTS:
    print('%s  %s%s' % ('PASS' if ok else 'FAIL', name,
                        '' if ok else '  -- ' + detail))

print('')
print('%d/%d passed' % (len(RESULTS) - len(FAILED), len(RESULTS)))

sys.exit(1 if FAILED else 0)
