#!/usr/bin/env python3
"""Run database migration 024 - Add profile_pic + date_of_birth to dll_access_relay."""

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
        with open('database/migrations/024_add_user_profile_fields.sql', 'r') as f:
            sql_script = f.read()

        print("Executing migration...")
        cursor.execute(sql_script)
        conn.commit()

        cursor.execute("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'dll_access_relay'
              AND column_name IN ('profile_pic', 'date_of_birth')
            ORDER BY column_name
        """)
        cols = cursor.fetchall()
        print("\nMigration 024 completed. New dll_access_relay columns:")
        for c in cols:
            print(f"   - {c[0]} ({c[1]})")
        cursor.close()
    except Exception as error:
        if conn:
            conn.rollback()
        print(f"[FATAL] Migration 024 failed: {error}")
        raise
    finally:
        if conn:
            conn.close()


if __name__ == '__main__':
    run_migration()
