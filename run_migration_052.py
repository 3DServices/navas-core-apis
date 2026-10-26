#!/usr/bin/env python3
"""Run database migration 052 - drivers.

Creates dll_drivers and dll_driver_assignments, which the /drivers registry
routes (endpoints/driver_registry.py) read and write. Only creates; changes no
existing row. Safe to run again.
"""

import psycopg2
from config import DB_LINK


def run_migration():
    conn = None
    try:
        print("Connecting to database...")
        conn = psycopg2.connect(DB_LINK)
        cur = conn.cursor()
        with open('database/migrations/052_drivers.sql', 'r',
                  encoding='utf-8') as handle:
            cur.execute(handle.read())
        conn.commit()
        print("Migration 052 applied.\n")

        for table in ('dll_drivers', 'dll_driver_assignments'):
            cur.execute("SELECT to_regclass(%s)", (table,))
            present = cur.fetchone()[0] is not None
            print(f"   {'ok   ' if present else 'CHECK'} {table}")
        cur.close()
    except Exception as error:
        if conn:
            conn.rollback()
        print(f"[FATAL] Migration 052 failed: {error}")
        raise
    finally:
        if conn:
            conn.close()


if __name__ == '__main__':
    run_migration()
