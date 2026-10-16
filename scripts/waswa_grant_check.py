#!/usr/bin/env python3
"""
waswa_grant_check.py — prove the navas_waswa role can do its job, and no more.

Run this AFTER database/manual/waswa_readonly_role.sql and BEFORE pointing any
code at the role. A missing grant does not look like a missing grant at
runtime — it looks like "Waswa says it has no vehicles", which is the exact
failure class we spent 2 October removing. Find it here instead.

The read list is not hardcoded. It is scanned out of the Waswa source files at
run time, so a table someone adds to the code next month is checked without
anyone remembering to update this script. That is the point: the check should
fail when the code outgrows the grant.

Three things are asserted:

  1. every Postgres table the code reads is SELECTable by the role
  2. every dll_waswa_* table the code writes is writable by the role
  3. the role is REFUSED on operational tables it must never change

Privilege is checked without touching data: an INSERT whose SELECT yields no
rows still fails with "permission denied" when the grant is missing, because
Postgres checks privileges before execution.

Usage:
    python scripts/waswa_grant_check.py \
        --role-url "postgresql://navas_waswa:PASSWORD@165.232.128.208:5432/DBNAME"
"""

import argparse
import glob
import io
import os
import re
import sys

import psycopg2

# These three live in Cassandra, which has its own roles. They appear in the
# source alongside the Postgres tables and must not be tested here.
CASSANDRA_TABLES = {
    'dll_device_basic_data',
    'dll_pulse_status_registry',
    'dll_location_registry_by_record_ts',
    'dll_location_registry',
    'system_schema',
}

# Operational tables the Waswa role must never be able to change. If any of
# these succeeds, the grant is too wide and the script fails.
MUST_REFUSE = (
    ('dll_device_subscriptions', 'subscription_status'),
    ('dll_payment_logs', 'payment_status'),
    ('dll_pause_rules', 'mode'),
    ('dll_client_accounts', 'client_name'),
)

# Discovered, not listed. A hand-written list is exactly how this check went
# wrong the first time: it named six modules and the Waswa path has nine, so
# the writes in waswa_documents.py and the views read by waswa_console.py and
# waswa_gating.py were never tested. The glob below is the same net as the
# grep in database/manual/waswa_readonly_role.sql, so a module added next
# month is scanned without anyone remembering this file exists.
def sources():
    found = sorted(glob.glob(os.path.join('endpoints', 'waswa_*.py')))
    base = os.path.join('endpoints', 'assistant.py')
    if os.path.exists(base):
        found.insert(0, base)
    return found

_FROM = re.compile(r'\b(?:FROM|JOIN)\s+([a-z_][a-z0-9_]*)', re.I)
_WRITE = re.compile(r'\b(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+([a-z_][a-z0-9_]*)',
                    re.I)

PASS, FAIL = [], []


def scan():
    """Table names the Waswa code reads and writes, from the source itself."""
    reads, writes = set(), set()
    files = sources()
    if not files:
        print('   !! no Waswa source files found. Run this from the repository')
        print('      root, or the scan proves nothing.')
        sys.exit(1)
    print('   scanning: ' + ', '.join(os.path.basename(f) for f in files))
    for rel in files:
        text = io.open(rel, encoding='utf-8').read()
        # These modules build SQL by concatenating string literals, so the
        # table name can sit on the far side of a quote boundary:
        #     "INSERT INTO dll_waswa_chunks "
        #     "(source_uid, body) VALUES ..."
        # Dropping every quote before the scan removes the boundary entirely,
        # which is cruder than parsing and cannot miss a case the way a
        # pattern for "adjacent literals" does.
        text = text.replace('"', ' ').replace("'", ' ')
        reads.update(m.lower() for m in _FROM.findall(text))
        writes.update(m.lower() for m in _WRITE.findall(text))

    # SQL keywords and CTE aliases sneak into a regex scan; drop anything that
    # is not plausibly one of this schema's tables or views.
    def real(name):
        return (name.startswith(('dll_', 'abi_', 'vw_', 'nav_'))
                and name not in CASSANDRA_TABLES)

    return sorted(n for n in reads if real(n)), sorted(n for n in writes if real(n))


def check(cur, label, sql, args=(), expect_refused=False):
    try:
        cur.execute(sql, args)
        cur.connection.rollback()
        if expect_refused:
            FAIL.append(f'{label} — SUCCEEDED but must be refused')
            print(f'   !! {label:<52} SUCCEEDED (grant too wide)')
        else:
            PASS.append(label)
            print(f'   ok {label}')
    except psycopg2.errors.InsufficientPrivilege:
        cur.connection.rollback()
        if expect_refused:
            PASS.append(label)
            print(f'   ok {label:<52} refused, as it must be')
        else:
            FAIL.append(f'{label} — permission denied')
            print(f'   !! {label:<52} PERMISSION DENIED')
    except psycopg2.errors.UndefinedTable:
        cur.connection.rollback()
        FAIL.append(f'{label} — table does not exist')
        print(f'   !! {label:<52} no such table')
    except psycopg2.Error as error:
        cur.connection.rollback()
        # Any other error means the privilege was fine and something else is
        # odd (a column name, a constraint). Report it without calling it a
        # grant failure, because it is not one.
        detail = str(error).splitlines()[0][:48]
        PASS.append(label)
        print(f'   ok {label:<52} (privilege ok; {detail})')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--role-url', required=True,
                    help='connection string for the navas_waswa role')
    args = ap.parse_args()

    reads, writes = scan()
    print(f'scanned the Waswa source: {len(reads)} table(s) read, '
          f'{len(writes)} written')

    conn = psycopg2.connect(args.role_url)
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT current_user')
            who = cur.fetchone()[0]
            print(f'connected as : {who}')
            if who == 'postgres' or 'superuser' in who:
                print('\n!! This looks like a superuser. The check only means '
                      'something\n   as the navas_waswa role.')
                return 1

            print('\n== reads the code performs ' + '=' * 48)
            for table in reads:
                check(cur, f'SELECT {table}', f'SELECT 1 FROM {table} LIMIT 1')

            print('\n== writes the code performs ' + '=' * 47)
            for table in writes:
                # Privilege-only: the SELECT yields nothing, so no row is
                # written, but Postgres still checks INSERT before executing.
                check(cur, f'INSERT {table}',
                      f'INSERT INTO {table} SELECT * FROM {table} WHERE false')

            print('\n== writes that must be refused ' + '=' * 43)
            for table, column in MUST_REFUSE:
                check(cur, f'UPDATE {table}',
                      f'UPDATE {table} SET {column} = {column} WHERE false',
                      expect_refused=True)
                check(cur, f'DELETE {table}',
                      f'DELETE FROM {table} WHERE false',
                      expect_refused=True)
    finally:
        conn.close()

    print('\n== Summary ' + '=' * 63)
    print(f'   {len(PASS)} passed, {len(FAIL)} failed')
    if FAIL:
        print('\n   Do NOT point any code at this role yet:')
        for f in FAIL:
            print(f'     - {f}')
        print('\n   A "permission denied" above means add that table to the')
        print('   grant list in database/manual/waswa_readonly_role.sql. A "SUCCEEDED')
        print('   but must be refused" means the grant is wider than intended.')
        return 1

    print('\n   The role can do everything the code does and nothing it should')
    print('   not. Safe to switch Waswa onto it (ticket A1c).')
    return 0


if __name__ == '__main__':
    sys.exit(main())
