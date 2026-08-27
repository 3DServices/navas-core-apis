#!/usr/bin/env python3
"""
Run database migration 022 - Create auto-renew settings table.
"""

import psycopg2
from config import DB_LINK


def run_migration():
    """Execute the migration SQL file."""
    conn = None
    try:
        print("Connecting to database...")
        conn = psycopg2.connect(DB_LINK)
        conn.autocommit = False
        cursor = conn.cursor()

        print("Reading migration file...")
        with open('database/migrations/022_create_auto_renew_settings.sql', 'r') as f:
            sql_script = f.read()

        print("Executing migration...")
        cursor.execute(sql_script)
        conn.commit()

        # Verify the table exists with the expected columns.
        cursor.execute("""
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_name = 'dll_auto_renew_settings'
            ORDER BY ordinal_position
        """)
        columns = cursor.fetchall()

        print("\n" + "=" * 70)
        print("Migration 022 completed successfully.")
        print("=" * 70)
        print("dll_auto_renew_settings columns:")
        for col in columns:
            print(f"   - {col[0]} ({col[1]}) nullable={col[2]} default={col[3]}")

        cursor.close()
    except Exception as error:
        if conn:
            conn.rollback()
        print(f"[FATAL] Migration 022 failed: {error}")
        raise
    finally:
        if conn:
            conn.close()


if __name__ == '__main__':
    run_migration()
