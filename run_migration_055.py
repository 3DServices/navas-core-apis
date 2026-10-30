#!/usr/bin/env python3
"""Run database migration 055 - fuel issue driver optional.

Lets dll_fuel_issues.driver_uid be empty, for fuel recorded without a driver.
Run after 053. Changes no existing row. Safe to run again.
"""

import psycopg2
from config import DB_LINK


def run_migration():
    conn = None
    try:
        print("Connecting to database...")
        conn = psycopg2.connect(DB_LINK)
        cur = conn.cursor()
        with open('database/migrations/055_fuel_driver_optional.sql', 'r',
                  encoding='utf-8') as handle:
            cur.execute(handle.read())
        conn.commit()
        print("Migration 055 applied.\n")

        cur.execute("""SELECT is_nullable FROM information_schema.columns
                        WHERE table_name = 'dll_fuel_issues'
                          AND column_name = 'driver_uid'""")
        row = cur.fetchone()
        nullable = row is not None and row[0] == 'YES'
        print(f"   {'ok   ' if nullable else 'CHECK'} dll_fuel_issues.driver_uid optional")
        cur.close()
    except Exception as error:
        if conn:
            conn.rollback()
        print(f"[FATAL] Migration 055 failed: {error}")
        raise
    finally:
        if conn:
            conn.close()


if __name__ == '__main__':
    run_migration()
