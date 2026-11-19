#!/usr/bin/env python3
"""Run database migration 056 - driver permit reminders.

Adds dll_driver_permit_reminders: the last permit-expiry reminder sent for
each driver (endpoints/permit_reminders.py). Run after 052. Changes no
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
        with open('database/migrations/056_driver_permit_reminders.sql', 'r',
                  encoding='utf-8') as handle:
            cur.execute(handle.read())
        conn.commit()
        print("Migration 056 applied.\n")

        cur.execute("SELECT to_regclass('dll_driver_permit_reminders')")
        ok = cur.fetchone()[0] is not None
        print(f"   {'ok   ' if ok else 'CHECK'} dll_driver_permit_reminders")
        cur.close()
    except Exception as error:
        if conn:
            conn.rollback()
        print(f"Migration 056 failed: {error}")
        raise
    finally:
        if conn:
            conn.close()


if __name__ == '__main__':
    run_migration()
