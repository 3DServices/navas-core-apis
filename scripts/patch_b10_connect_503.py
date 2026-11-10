#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
B10 / Layer 2 -- trips_history's database connect fails honestly.

endpoints/data.py:1141 opens the route's Postgres connection with no handler
of its own:

    dbconnect = psycopg2.connect(current_app.config['db_link'])

When it raises, the failure falls through to the function's catch-all, which
returns HTTP 500 with the exception text.  Two problems:

  * 500 tells the client the request itself is broken and must not be
    retried.  That is the wrong answer here -- scripts/audit_db_host_health.py
    got 10/10 on sequential connects, so a connect failure on this host is a
    transient condition and a retry very likely succeeds.  503 is the honest
    code, and it is what the Cassandra paths in this same route already
    return (data.py:1191, 1219).
  * the exception text is psycopg2's, which is where the credential leak
    Layer 1 now scrubs comes from.  Not raising it to the caller at all is
    better than scrubbing it.

The real error still goes to the log in full, via logging.exception.

NOTE on scoping: the same `dbconnect = psycopg2.connect(...)` line appears 20
times in data.py.  Every edit here is confined to the trips_history() line
range, resolved with ast -- the mistake patch_b5_config_cache.py made by
using str.replace() on the whole file is not repeated.

Dry run by default.  Pass --apply to write.
"""

import argparse
import ast
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TARGET = os.path.join(ROOT, 'endpoints', 'data.py')
FUNCTION = 'trips_history'


def read_source(path):
    with io.open(path, 'rb') as handle:
        text = handle.read().decode('utf-8')
    return text.replace('\r\n', '\n'), ('\r\n' in text)


def write_source(path, text, crlf):
    out = text.replace('\n', '\r\n') if crlf else text
    with io.open(path, 'wb') as handle:
        handle.write(out.encode('utf-8'))


def function_range(text, name):
    tree = ast.parse(text)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            lines = text.split('\n')
            start = sum(len(l) + 1 for l in lines[:node.lineno - 1])
            end = sum(len(l) + 1 for l in lines[:node.end_lineno])
            return start, end, node.lineno, node.end_lineno
    raise SystemExit('FAIL: def %s() not found in %s' % (name, TARGET))


OLD = "        dbconnect = psycopg2.connect(current_app.config['db_link'])\n"

NEW = (
    "        try:\n"
    "            dbconnect = psycopg2.connect(current_app.config['db_link'])\n"
    "        except Exception:\n"
    "            # Transient on this host -- 10/10 sequential connects succeeded in\n"
    "            # scripts/audit_db_host_health.py -- so tell the client to retry\n"
    "            # rather than letting the catch-all answer 500 with psycopg2's\n"
    "            # text, which quotes the DSN.  Full error goes to the log.\n"
    "            logging.exception('trips_history: database connection failed')\n"
    "            return reply('error', 503,\n"
    "                         'Trip history is temporarily unavailable, please retry', '')\n"
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()

    text, crlf = read_source(TARGET)
    before_lines = text.count('\n') + 1

    start, end, first_line, last_line = function_range(text, FUNCTION)
    body = text[start:end]

    if 'except Exception:\n            # Transient on this host' in body:
        print('SKIP: trips_history() connect is already guarded.')
        return 0

    # Count WHOLE LINES, not substrings.  OLD is indented 8 spaces and the
    # replacement re-indents it to 12, so the 8-space form is a substring of
    # the 12-space form -- str.count() cannot tell the two apart and reported
    # "0 changed" on a correct edit.
    def count_exact(blob):
        target = OLD.rstrip('\n')
        return sum(1 for line in blob.split('\n') if line == target)

    occurrences = count_exact(body)
    if occurrences != 1:
        print('FAIL: expected exactly 1 unguarded connect inside %s(), found %d'
              % (FUNCTION, occurrences))
        return 1

    whole_before = count_exact(text)

    patched_body = body.replace(OLD, NEW, 1)
    text = text[:start] + patched_body + text[end:]

    whole_after = count_exact(text)
    if whole_before - whole_after != 1:
        print('FAIL: edit changed %d occurrences file-wide, expected 1'
              % (whole_before - whole_after))
        return 1

    try:
        compile(text, TARGET, 'exec')
    except SyntaxError as error:
        print('FAIL: patched source does not compile: %s' % error)
        return 1

    # confirm the guard really landed inside trips_history()
    start2, end2, _f2, _l2 = function_range(text, FUNCTION)
    if "return reply('error', 503,\n" not in text[start2:end2]:
        print('FAIL: the 503 guard is not inside %s() after the edit' % FUNCTION)
        return 1

    print('endpoints/data.py  %s' % ('CRLF' if crlf else 'LF'))
    print('  %s() spans lines %d-%d' % (FUNCTION, first_line, last_line))
    print('  guarded the 1 connect inside it; %d other connects in the file left alone'
          % whole_after)
    print('  %d -> %d lines' % (before_lines, text.count('\n') + 1))

    if not args.apply:
        print('\nDRY RUN -- nothing written.  Re-run with --apply.')
        return 0

    write_source(TARGET, text, crlf)
    print('\nWRITTEN.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
