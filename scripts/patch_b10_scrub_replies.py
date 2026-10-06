#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
B10 / Layer 1 -- stop credentials reaching API callers.

scripts/audit_error_leaks.py found 71 handlers that hand str(error) straight
back to the caller as reply('error', 500, str(error), ''), and reply() itself
performs no sanitisation whatsoever -- message_body goes directly into
jsonify().  Probing with a fake DSN showed that a MALFORMED db_link makes
psycopg2 echo the password verbatim:

    invalid dsn: missing "=" after "postgresql:/user:NOT_A_REAL_PASSWORD_9f3a@host...

That is latent, not active: production reads a well-formed .env.  But it is
one typo away from publishing the database password over HTTP.

This patch closes it at the single chokepoint every one of those 71 handlers
goes through:

  1. add `import logging` / `import re` to endpoints/globals.py
  2. insert scrub_secrets(text, extra=()) -- a PURE function, no Flask, no
     database, no module state, so it is unit-testable on its own
  3. insert _configured_secrets() -- pulls the password out of
     current_app.config['db_link'], URI form *or* keyword-DSN form
  4. route reply()'s message_body through the scrubber

Only credential-shaped text is touched.  Every other byte of every message is
left exactly as it was, so the wording of all 71 responses -- including every
validation message a client may be matching on -- is unchanged.

Dry run by default.  Pass --apply to write.
"""

import argparse
import ast
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TARGET = os.path.join(ROOT, 'endpoints', 'globals.py')


# ---------------------------------------------------------------- file helpers

def read_source(path):
    with io.open(path, 'rb') as handle:
        raw = handle.read()
    text = raw.decode('utf-8')
    crlf = '\r\n' in text
    return text.replace('\r\n', '\n'), crlf


def write_source(path, text, crlf):
    out = text.replace('\n', '\r\n') if crlf else text
    with io.open(path, 'wb') as handle:
        handle.write(out.encode('utf-8'))


def function_range(text, name):
    """Return (start_index, end_index) of a module-level def, LF text."""
    tree = ast.parse(text)
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            lines = text.split('\n')
            start = sum(len(l) + 1 for l in lines[:node.lineno - 1])
            end = sum(len(l) + 1 for l in lines[:node.end_lineno])
            return start, end
    raise SystemExit('FAIL: module-level def %s() not found in %s' % (name, TARGET))


# ------------------------------------------------------------------ new source

IMPORTS = 'import logging\nimport re\n'

HELPER = '''# ==========================================
# CREDENTIAL SCRUBBER  (B10)
# ==========================================
#
# Every error path in this codebase funnels through reply().  71 handlers pass
# str(error) as the message body, and a malformed db_link makes psycopg2 quote
# the password back inside its own error text.  scrub_secrets() is the single
# place that gets removed.
#
# It is deliberately a PURE function -- no Flask, no database, no module state
# -- so tests/test_reply_scrub.py can exercise it without an app context.

# scheme://user:password@host   and the malformed  scheme:/user:password@host
_CREDENTIAL_URI = re.compile(
    r'(?P<scheme>[A-Za-z][A-Za-z0-9+.\\-]*:/{1,3})(?P<user>[^\\s:/@]*):(?P<secret>[^\\s@]+)@'
)

# psycopg2 keyword DSN form:  dbname=x user=y password=z host=w
_CREDENTIAL_KEYWORD = re.compile(r'(?P<key>password\\s*=\\s*)(?P<secret>\\S+)')

# Only treat `password=` as a DSN field when another libpq keyword is present.
# Without this guard an ordinary sentence -- "Invalid password = required" --
# would be rewritten, which would change a message for no security gain.  The
# configured-secret pass still covers a lone `password=SECRET`.
_DSN_CONTEXT = re.compile(r'\\b(?:dbname|host|hostaddr|port|user|sslmode|options)\\s*=')

REDACTED = '***'


def scrub_secrets(text, extra=()):
    """Remove credentials from a value before it leaves the process.

    Three passes, in order:
      1. scheme://user:password@host  ->  scheme://user:***@host
      2. password=SECRET  ->  password=***  (only inside a libpq DSN)
      3. every literal in `extra` (the configured secrets) -> ***

    Pass 3 is the backstop: it catches a secret embedded in a shape passes 1
    and 2 do not recognise.  Strings shorter than 4 characters are skipped so
    a trivially short configured value cannot blank out unrelated text.

    Containers are walked so a handler that nests the error text one level
    deep is covered too.  Types are preserved; anything that is not a string
    or a container is returned untouched.
    """
    if isinstance(text, str):
        cleaned = _CREDENTIAL_URI.sub(
            lambda m: m.group('scheme') + m.group('user') + ':' + REDACTED + '@',
            text,
        )
        if _DSN_CONTEXT.search(cleaned):
            cleaned = _CREDENTIAL_KEYWORD.sub(
                lambda m: m.group('key') + REDACTED,
                cleaned,
            )
        for secret in (extra or ()):
            if isinstance(secret, str) and len(secret) >= 4:
                cleaned = cleaned.replace(secret, REDACTED)
        return cleaned

    if isinstance(text, dict):
        return dict((key, scrub_secrets(value, extra)) for key, value in text.items())

    if isinstance(text, list):
        return [scrub_secrets(item, extra) for item in text]

    if isinstance(text, tuple):
        return tuple(scrub_secrets(item, extra) for item in text)

    return text


def _configured_secrets():
    """The secret halves of this app's configured db_link, as literals.

    Never raises: outside an app context, or with db_link absent, it simply
    returns an empty tuple and pattern matching alone does the work.
    """
    secrets = []

    try:
        if not has_app_context():
            return ()

        link = current_app.config.get('db_link')

        if link:
            link = str(link)

            found = _CREDENTIAL_URI.search(link)

            if found:
                secrets.append(found.group('secret'))

            found = _CREDENTIAL_KEYWORD.search(link)

            if found:
                secrets.append(found.group('secret'))

    except Exception:
        return tuple(secrets)

    return tuple(secrets)


'''

OLD_REPLY = '''def reply(status, status_code, message_body, data):

    data_object = {
        "status": status,
        "message": message_body,
        "data": data
    }

    return jsonify(data_object), status_code'''

NEW_REPLY = '''def reply(status, status_code, message_body, data):

    safe_message = scrub_secrets(message_body, _configured_secrets())

    if safe_message != message_body:
        logging.warning(
            'reply(): credentials redacted from a %s response body', status_code
        )

    data_object = {
        "status": status,
        "message": safe_message,
        "data": data
    }

    return jsonify(data_object), status_code'''


# ----------------------------------------------------------------------- patch

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true', help='write the file')
    args = parser.parse_args()

    text, crlf = read_source(TARGET)
    original = text
    steps = []

    if 'def scrub_secrets(' in text:
        print('SKIP: scrub_secrets() already present -- nothing to do.')
        return 0

    # 1. imports
    anchor = 'from .jwt_utils import decode_access_token\n'
    if anchor not in text:
        raise SystemExit('FAIL: import anchor not found')
    if 'import logging\n' in text or 'import re\n' in text:
        raise SystemExit('FAIL: logging/re already imported -- resolve by hand')
    text = text.replace(anchor, IMPORTS + anchor, 1)
    steps.append('added `import logging` and `import re`')

    # 2+3. helper block, inserted immediately above reply()
    start, _end = function_range(text, 'reply')
    text = text[:start] + HELPER + text[start:]
    steps.append('inserted scrub_secrets() and _configured_secrets() above reply()')

    # 4. reply() itself -- scoped strictly to the reply() line range
    start, end = function_range(text, 'reply')
    current = text[start:end].rstrip('\n')
    if current != OLD_REPLY:
        print('FAIL: reply() is not the text this patch expects.')
        print('--- found ---')
        print(current)
        print('--- expected ---')
        print(OLD_REPLY)
        return 1
    text = text[:start] + NEW_REPLY + '\n' + text[end:]
    steps.append('reply() now scrubs message_body')

    # compile before writing
    try:
        compile(text, TARGET, 'exec')
    except SyntaxError as error:
        print('FAIL: patched source does not compile: %s' % error)
        return 1

    print('endpoints/globals.py  %s  %d -> %d lines' % (
        'CRLF' if crlf else 'LF',
        original.count('\n') + 1,
        text.count('\n') + 1,
    ))
    for step in steps:
        print('  * %s' % step)

    if not args.apply:
        print('\nDRY RUN -- nothing written.  Re-run with --apply.')
        return 0

    write_source(TARGET, text, crlf)
    print('\nWRITTEN.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
