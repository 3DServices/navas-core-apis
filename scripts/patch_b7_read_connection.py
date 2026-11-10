#!/usr/bin/env python3
"""
patch_b7_read_connection.py — one Postgres connection per request, for reads.

Ticket B7. The measured problem: psycopg2._connect ran three times in a single
trips_history request, 2.32s each, ~7s of the 29.72s. trips_history opens one
connection, then check_device and CheckHardware2 each open their own, against
a host in Kampala where a connect costs over two seconds.

What the audit found, and what it did NOT
-----------------------------------------
I expected a connection leak: 190 functions across this codebase open more
connections than they close, and `with dbconnect:` commits without closing.
The live server says otherwise — 2 idle connections on this database, none
stale beyond five minutes, and max_connections is 50,000. In CPython the
local goes out of scope when the function returns and psycopg2 closes the
connection in __del__. Fragile (it would leak under a different interpreter,
or when a traceback keeps a frame alive) but not the leak I predicted. So this
is a latency fix, not a stability one, and the scope is set accordingly.

Why only these three helpers
----------------------------
A shared connection changes transaction semantics. Every one of those
functions does `with dbconnect:`, which COMMITS — so sharing a connection
between a writer and anything else means one function's commit flushes
another's in-flight work. That is a data-integrity change wearing an
optimisation's clothes.

check_device, CheckHardware and CheckHardware2 are pure SELECTs. Verified by
reading all three: no INSERT, UPDATE or DELETE anywhere in them. So they can
share a connection safely, and the 190 writers are left alone — they need a
pool plus per-function review of what each transaction actually spans, which
is a separate ticket, not a rider on this one.

The connection is reserved for those three by convention and by the comment on
the g key. Handing it to a writer would reintroduce exactly the problem this
patch declines to cause.

Changes
-------
1. globals.py gains _read_connection(), which keeps one connection on flask.g
   per app context, and close_read_connection() for teardown.
2. The three helpers take their connection from it instead of opening one.
3. app.py registers the teardown, so the connection is closed explicitly
   rather than left to refcounting — the practice the audit flagged.

Outside an app context (a script importing globals) a fresh connection is
returned, so nothing that works today stops working.

    python scripts/patch_b7_read_connection.py            # dry run
    python scripts/patch_b7_read_connection.py --apply
"""

import argparse
import difflib
import io
import os
import re
import shutil
import sys
import time

GLOBALS = os.path.join('endpoints', 'globals.py')
APP = 'app.py'
HELPERS = ('check_device', 'CheckHardware', 'CheckHardware2')

OLD_CONNECT = "    dbconnect = psycopg2.connect(current_app.config['db_link'])\n"
NEW_CONNECT = "    dbconnect = _read_connection()\n"

HELPER_CODE = '''
# ── One connection per request, for the read-only device lookups ────────────
# check_device, CheckHardware and CheckHardware2 are called several times per
# request and each used to open its own connection. Against this host a
# connect costs ~2.3s, so a single trips_history request spent ~7s of its 30
# doing nothing but handshakes.
#
# RESERVED FOR READS. These three helpers are pure SELECTs. Do NOT hand this
# connection to anything that writes: every caller wraps its work in
# `with dbconnect:`, which COMMITS, so a writer sharing this connection would
# commit whatever else happened to be pending on it. The ~190 functions in
# this codebase that open their own connection need a pool and a review of
# what each transaction spans; that is deliberately not this change.
_READ_CONN_KEY = '_navas_read_only_connection'


def _read_connection():
    """The request's shared read-only connection, opening it on first use.

    Outside an app context — a script importing this module — a fresh
    connection is returned instead, so existing callers keep working.
    """
    if not has_app_context():
        return psycopg2.connect(current_app.config['db_link'])
    existing = getattr(g, _READ_CONN_KEY, None)
    if existing is not None and not existing.closed:
        return existing
    fresh = psycopg2.connect(current_app.config['db_link'])
    setattr(g, _READ_CONN_KEY, fresh)
    return fresh


def close_read_connection(_exception=None):
    """Close the shared read connection at the end of the app context.

    Registered in app.py. Without this the connection would be left to
    CPython's refcounting, which is what the audit flagged as fragile even
    though it currently works.
    """
    existing = getattr(g, _READ_CONN_KEY, None) if has_app_context() else None
    if existing is None:
        return
    try:
        if not existing.closed:
            existing.close()
    except Exception:                                   # noqa: BLE001
        pass
    try:
        setattr(g, _READ_CONN_KEY, None)
    except Exception:                                   # noqa: BLE001
        pass

'''

APP_ANCHOR = "app.config['db_link'] = DB_LINK\n"
APP_CODE = '''

# Close the shared read-only connection (endpoints/globals.py) when the app
# context ends, instead of leaving it to refcounting.
from endpoints.globals import close_read_connection as _close_read_connection
app.teardown_appcontext(_close_read_connection)
'''


def func_range(lines, name):
    start = next((i for i, l in enumerate(lines)
                  if re.match(rf'def {name}\(', l)), None)
    if start is None:
        return None, None
    end = next((j for j in range(start + 1, len(lines))
                if re.match(r'def \w+\(|@\w+\.route\(', lines[j])), len(lines))
    return start, end


def load(path):
    raw = io.open(path, encoding='utf-8', newline='').read()
    crlf = raw.count('\r\n') > raw.count('\n') // 2
    return (raw.replace('\r\n', '\n') if crlf else raw), crlf


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    args = ap.parse_args()

    for path in (GLOBALS, APP):
        if not os.path.exists(path):
            print(f'!! {path} not found. Run from the repository root.')
            return 1

    src, crlf = load(GLOBALS)
    print(f'{GLOBALS} line endings : {"CRLF" if crlf else "LF"}')
    if '_read_connection()' in src:
        print('Already patched. Nothing to do.')
        return 0

    lines = src.splitlines(keepends=True)

    # Replace the connect line inside each helper's own range, never globally:
    # the identical line appears in ~190 functions, and a global replace would
    # hand this read connection to every writer in the file. That is the
    # mistake patch_b5_config_cache made by using replace(..., 1).
    edits = []
    for name in HELPERS:
        lo, hi = func_range(lines, name)
        if lo is None:
            print(f'!! def {name}( not found in {GLOBALS}')
            return 1
        hits = [i for i in range(lo, hi) if lines[i] == OLD_CONNECT]
        if len(hits) != 1:
            print(f'!! {name}(): expected 1 connect line, found {len(hits)}')
            return 1
        body = ''.join(lines[lo:hi]).upper()
        for word in ('INSERT ', 'UPDATE ', 'DELETE ', 'TRUNCATE '):
            if word in body:
                print(f'!! {name}() contains {word.strip()}; it is not a '
                      f'pure reader. Refusing.')
                return 1
        edits.append((name, hits[0]))
        print(f'   {name}(): lines {lo + 1}-{hi}, connect at {hits[0] + 1}, '
              f'no write keywords')

    out = list(lines)
    for _name, i in edits:
        out[i] = NEW_CONNECT

    new = ''.join(out)
    if 'has_app_context' not in new:
        if 'from flask import g\n' not in new:
            print('!! "from flask import g" not found to anchor the import')
            return 1
        new = new.replace('from flask import g\n',
                          'from flask import g\n'
                          'from flask import has_app_context\n', 1)

    first = min(i for _n, i in edits)
    at = next(j for j in range(first, -1, -1)
              if re.match(r'def \w+\(', new.splitlines(keepends=True)[j]))
    pieces = new.splitlines(keepends=True)
    new = ''.join(pieces[:at]) + HELPER_CODE.lstrip('\n') + '\n' + \
        ''.join(pieces[at:])

    try:
        compile(new, GLOBALS, 'exec')
    except SyntaxError as error:
        print(f'!! {GLOBALS} does not compile: line {error.lineno}: '
              f'{error.msg}')
        return 1

    app_src, app_crlf = load(APP)
    if '_close_read_connection' in app_src:
        app_new = app_src
        print(f'\n{APP}: teardown already registered')
    else:
        if app_src.count(APP_ANCHOR) != 1:
            print(f'!! {APP}: anchor matched '
                  f'{app_src.count(APP_ANCHOR)} time(s)')
            return 1
        app_new = app_src.replace(APP_ANCHOR, APP_ANCHOR + APP_CODE, 1)
        try:
            compile(app_new, APP, 'exec')
        except SyntaxError as error:
            print(f'!! {APP} does not compile: line {error.lineno}: '
                  f'{error.msg}')
            return 1
    print('both files compile')

    for path, before, after in ((GLOBALS, src, new), (APP, app_src, app_new)):
        if before == after:
            continue
        print(f'\n--- {path}')
        for line in difflib.unified_diff(before.splitlines(),
                                         after.splitlines(),
                                         fromfile=f'{path} (now)',
                                         tofile=f'{path} (patched)',
                                         lineterm='', n=2):
            print(line)

    if not args.apply:
        print('\n--- DRY RUN. Nothing written. ---')
        print('    python scripts/patch_b7_read_connection.py --apply')
        return 0

    stamp = time.strftime('%Y%m%d-%H%M%S')
    for path, after, is_crlf in ((GLOBALS, new, crlf),
                                 (APP, app_new, app_crlf)):
        shutil.copy2(path, f'{path}.bak.{stamp}')
        io.open(path, 'w', encoding='utf-8', newline='').write(
            after.replace('\n', '\r\n') if is_crlf else after)
    print(f'\nwritten. backups at *.bak.{stamp}')
    print('\nThen measure:')
    print('  python scripts/b5_measure.py')
    print('\nExpect "PG connections" to fall from 3 to 1, the response to be')
    print('IDENTICAL to the last run, and ~4.6s off the wall time.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
