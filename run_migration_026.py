#!/usr/bin/env python3
"""Run database migration 026 - Unit-level pause rules + pause events."""

import psycopg2
from config import DB_LINK


def run_migration():
    conn = None
    try:
        print("Connecting to database...")
        conn = psycopg2.connect(DB_LINK)
        conn.autocommit = False
        cursor = conn.cursor()

        print("Reading migration file...")
        with open('database/migrations/026_unit_pause_rules_events.sql', 'r') as f:
            sql_script = f.read()

        print("Executing migration...")
        cursor.execute(sql_script)
        conn.commit()

        for table in ('dll_pause_rules', 'dll_pause_events'):
            cursor.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name=%s ORDER BY ordinal_position", (table,))
            cols = [c[0] for c in cursor.fetchall()]
            print(f"\n{table}: {', '.join(cols)}")
        cursor.close()
    except Exception as error:
        if conn:
            conn.rollback()
        print(f"[FATAL] Migration 026 failed: {error}")
        raise
    finally:
        if conn:
            conn.close()


if __name__ == '__main__':
    run_migration()
