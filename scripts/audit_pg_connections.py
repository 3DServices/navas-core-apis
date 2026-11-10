#!/usr/bin/env python3
"""
audit_pg_connections.py — three connections per request, or a leak?

B7 started as "7 seconds of the remaining 29.72s": psycopg2._connect ran three
times at 2.32s each in the profile, because trips_history opens one connection
and then check_device and CheckHardware2 each open their own.

But check_device looks like this:

    dbconnect = psycopg2.connect(current_app.config['db_link'])
    with dbconnect:
        with dbconnect.cursor() as cursor:
            ...
            return BillingStatus

`with dbconnect:` commits or rolls back. It does NOT close the connection.
psycopg2 is explicit about that. So if nothing calls .close(), every call
leaks a Postgres connection until the object is garbage collected — and under
load that exhausts max_connections long before it costs anybody 2.3 seconds.

That changes B7 from a latency ticket into a stability one, so it has to be
established rather than assumed. This reports:

  1. every psycopg2.connect() in the codebase, and whether that function
     also closes what it opened
  2. how many places call check_device / CheckHardware / CheckHardware2 —
     the blast radius of changing their signatures
  3. the live server's max_connections against what is currently open, and
     how many of those are idle — a pile of idle connections from this app
     is the leak, visible
  4. whether psycopg2.pool is available, since a module-level pool fixes
     every call site at once with no signature changes

Read-only. Nothing is written, no connection is terminated.

Usage:
    python scripts/audit_pg_connections.py
"""

import argparse
import ast
import io
import os
import re
import sys
from collections import Counter

import psycopg2

sys.path.insert(0, '.')
from config import DB_LINK                              # noqa: E402

HELPERS = ('check_device', 'CheckHardware2', 'CheckHardware',
           'resolve_wallet_owner')


def py_files():
    out = []
    for folder in ('endpoints', '.'):
        if not os.path.isdir(folder):
            continue
        for name in sorted(os.listdir(folder)):
            if name.endswith('.py'):
                path = os.path.join(folder, name)
                if os.path.isfile(path):
                    out.append(path)
        if folder == '.':
            break
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.parse_args()

    print('=' * 72)
    print('1. WHO OPENS A CONNECTION, AND DOES THEY CLOSE IT?')
    print('=' * 72)
    opens_total = closes_total = 0
    leaky = []
    for path in py_files():
        try:
            tree = ast.parse(io.open(path, encoding='utf-8',
                                     errors='ignore').read())
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            body = ast.dump(node)
            opens = body.count("attr='connect'")
            if not opens:
                continue
            closes = body.count("attr='close'")
            opens_total += opens
            closes_total += closes
            if closes < opens:
                leaky.append((path, node.name, node.lineno, opens, closes))
    print(f'   functions that open a connection : '
          f'{opens_total} open call(s) in total')
    print(f'   close() calls in those functions : {closes_total}')
    print(f'\n   opens MORE than it closes: {len(leaky)} function(s)')
    for path, name, line, opens, closes in leaky[:25]:
        print(f'      {path}:{line}  {name}()  '
              f'opens {opens}, closes {closes}')
    if len(leaky) > 25:
        print(f'      ... and {len(leaky) - 25} more')
    if leaky:
        print('\n   `with dbconnect:` commits; it does NOT close. Each of')
        print('   these holds a Postgres backend open until the object is')
        print('   collected.')

    print('\n' + '=' * 72)
    print('2. BLAST RADIUS OF THE HELPERS')
    print('=' * 72)
    calls = Counter()
    where = {}
    for path in py_files():
        text = io.open(path, encoding='utf-8', errors='ignore').read()
        for helper in HELPERS:
            found = len(re.findall(rf'\b{helper}\s*\(', text))
            # subtract its own definition
            found -= len(re.findall(rf'def {helper}\s*\(', text))
            if found > 0:
                calls[helper] += found
                where.setdefault(helper, []).append(f'{path}({found})')
    for helper in HELPERS:
        if calls[helper]:
            print(f'   {helper:<22} {calls[helper]:>3} call site(s)')
            print(f'      {", ".join(where[helper])}')
    print('\n   -> changing a signature touches every one of these. A')
    print('      module-level pool touches none.')

    print('\n' + '=' * 72)
    print('3. THE LIVE SERVER: IS THE LEAK VISIBLE?')
    print('=' * 72)
    conn = psycopg2.connect(DB_LINK)
    try:
        with conn.cursor() as cur:
            cur.execute("SHOW max_connections")
            cap = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM pg_stat_activity")
            total = cur.fetchone()[0]
            print(f'   max_connections        : {cap}')
            print(f'   currently connected    : {total}')
            cur.execute("""
                SELECT state, count(*)
                  FROM pg_stat_activity
                 WHERE datname = current_database()
                 GROUP BY state ORDER BY 2 DESC""")
            print('\n   by state, this database:')
            for state, n in cur.fetchall():
                print(f'      {str(state):<24} {n}')
            cur.execute("""
                SELECT application_name, state,
                       count(*),
                       max(now() - state_change)::text
                  FROM pg_stat_activity
                 WHERE datname = current_database()
                 GROUP BY 1, 2 ORDER BY 3 DESC LIMIT 8""")
            print('\n   by application, with the oldest in that state:')
            for app, state, n, oldest in cur.fetchall():
                print(f'      {str(app)[:22]:<22} {str(state):<20} '
                      f'{n:>4}  oldest {oldest}')
            idle = [r for r in () ]
            cur.execute("""
                SELECT count(*) FROM pg_stat_activity
                 WHERE datname = current_database()
                   AND state = 'idle'
                   AND now() - state_change > interval '5 minutes'""")
            stale = cur.fetchone()[0]
            print(f'\n   idle for over 5 minutes: {stale}')
            if stale > 5:
                print('   -> that is the leak. Connections nobody is using and')
                print('      nobody closed.')
            else:
                print('   -> no large pile of stale connections right now.')
                print('      With one developer testing that proves little;')
                print('      the code pattern is the evidence, not the count.')
    finally:
        conn.close()

    print('\n' + '=' * 72)
    print('4. IS A POOL AVAILABLE?')
    print('=' * 72)
    try:
        from psycopg2 import pool as pg_pool
        for name in ('SimpleConnectionPool', 'ThreadedConnectionPool'):
            print(f'   psycopg2.pool.{name}: '
                  + ('available' if hasattr(pg_pool, name) else 'MISSING'))
        print('\n   A ThreadedConnectionPool in globals.py, handed out and')
        print('   returned by a context manager, fixes every call site at')
        print('   once: no signature changes, no caller edits, and the leak')
        print('   closes because returning to the pool is the release.')
    except Exception as error:                          # noqa: BLE001
        print(f'   !! {error}')

    print('\n' + '=' * 72)
    print('WHAT B7 IS')
    print('=' * 72)
    print('   If section 1 shows many functions opening without closing,')
    print('   B7 is a connection leak with a latency symptom, not a latency')
    print('   ticket. The fix is a pool plus a context manager, which is')
    print('   smaller than threading a connection through the call sites in')
    print('   section 2 and fixes the ones this route never touches.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
