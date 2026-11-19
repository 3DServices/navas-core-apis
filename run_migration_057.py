#!/usr/bin/env python3
"""Run database migration 057 - fuel voucher number.

Adds dll_fuel_issues.voucher_number (optional) and its one-use-per-client
index. Run after 053. Changes no existing row. Safe to run again.
"""

import psycopg2
from config import DB_LINK


def run_migration():
    conn = None
    try:
        print("Connecting to database...")
        conn = psycopg2.connect(DB_LINK)
        cur = conn.cursor()
        with open('database/migrations/057_fuel_voucher_number.sql', 'r',
                  encoding='utf-8') as handle:
            cur.execute(handle.read())
        conn.commit()
        print("Migration 057 applied.\n")

        cur.execute("""SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'dll_fuel_issues'
                          AND column_name = 'voucher_number'""")
        ok = cur.fetchone() is not None
        print(f"   {'ok   ' if ok else 'CHECK'} dll_fuel_issues.voucher_number")
        cur.close()
    except Exception as error:
        if conn:
            conn.rollback()
        print(f"Migration 057 failed: {error}")
        raise
    finally:
        if conn:
            conn.close()


if __name__ == '__main__':
    run_migration()
