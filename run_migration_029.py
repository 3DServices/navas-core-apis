#!/usr/bin/env python3
"""Run database migration 029 - Create the reverse-geocode cache table."""

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
        with open('database/migrations/029_create_geocode_cache.sql', 'r') as f:
            sql_script = f.read()

        print("Executing migration...")
        cursor.execute(sql_script)
        conn.commit()

        cursor.execute("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'dll_geocode_cache'
            ORDER BY ordinal_position
        """)
        cols = cursor.fetchall()
        print("\nMigration 029 completed. dll_geocode_cache columns:")
        for c in cols:
            print(f"   - {c[0]} ({c[1]})")
        cursor.close()
    except Exception as error:
        if conn:
            conn.rollback()
        print(f"[FATAL] Migration 029 failed: {error}")
        raise
    finally:
        if conn:
            conn.close()


if __name__ == '__main__':
    run_migration()
