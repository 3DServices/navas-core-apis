#!/usr/bin/env python3
"""Run database migration 023 - Create auto-renew audit log table."""

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
        with open('database/migrations/023_create_auto_renew_log.sql', 'r') as f:
            sql_script = f.read()

        print("Executing migration...")
        cursor.execute(sql_script)
        conn.commit()

        cursor.execute("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'dll_auto_renew_log'
            ORDER BY ordinal_position
        """)
        cols = cursor.fetchall()
        print("\nMigration 023 completed. dll_auto_renew_log columns:")
        for c in cols:
            print(f"   - {c[0]} ({c[1]})")
        cursor.close()
    except Exception as error:
        if conn:
            conn.rollback()
        print(f"[FATAL] Migration 023 failed: {error}")
        raise
    finally:
        if conn:
            conn.close()


if __name__ == '__main__':
    run_migration()
