#!/usr/bin/env python3
"""Run database migration 058 - client branding.

Adds dll_client_branding (a client's colours and assistant name, and the
CMS switches for who may change them) and the branding.control /
branding.override staff permissions. Changes no existing row. Safe to run
again.

If Waswa runs on its own read-only login (WASWA_DATABASE_URL), re-run
database/manual/waswa_readonly_role.sql afterwards so it can read the
assistant's name; until then Waswa keeps calling itself Waswa.
"""

import psycopg2
from config import DB_LINK


def run_migration():
    conn = None
    try:
        print("Connecting to database...")
        conn = psycopg2.connect(DB_LINK)
        cur = conn.cursor()
        with open('database/migrations/058_client_branding.sql', 'r',
                  encoding='utf-8') as handle:
            cur.execute(handle.read())
        conn.commit()
        print("Migration 058 applied.\n")

        cur.execute("SELECT to_regclass('dll_client_branding')")
        table = cur.fetchone()[0] is not None
        cur.execute("SELECT COUNT(*) FROM dll_permissions WHERE permission_name IN "
                    "('branding.control', 'branding.override')")
        perms = cur.fetchone()[0]
        print(f"   {'ok   ' if table else 'CHECK'} dll_client_branding")
        print(f"   {'ok   ' if perms == 2 else 'CHECK'} branding permissions ({perms} of 2)")
        cur.close()
    except Exception as error:
        if conn:
            conn.rollback()
        print(f"Migration 058 failed: {error}")
        raise
    finally:
        if conn:
            conn.close()


if __name__ == '__main__':
    run_migration()
