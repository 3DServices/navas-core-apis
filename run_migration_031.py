#!/usr/bin/env python3
"""Run database migration 031 - customer_class on dll_client_accounts."""

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
        with open('database/migrations/031_customer_class.sql', 'r') as f:
            sql_script = f.read()

        print("Executing migration...")
        cursor.execute(sql_script)
        conn.commit()

        cursor.execute("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'dll_client_accounts'
              AND column_name IN ('customer_class', 'class_assigned_by',
                                  'class_assigned_at', 'class_note')
            ORDER BY ordinal_position
        """)
        print("\nMigration 031 completed. Columns added:")
        for name, dtype in cursor.fetchall():
            print(f"   - {name} ({dtype})")

        cursor.execute("""
            SELECT COUNT(*),
                   COUNT(*) FILTER (WHERE customer_class IS NOT NULL)
            FROM dll_client_accounts
            WHERE is_deleted = FALSE OR is_deleted IS NULL
        """)
        total, assigned = cursor.fetchone()
        print(f"\n   {assigned} of {total} active clients have a class assigned.")
        if assigned == 0:
            print("   None assigned yet — this is expected. Waswa will keep")
            print("   reporting customer_class as unknown until they are set.")
            print("   SELECT * FROM vw_waswa_class_advisory ORDER BY "
                  "subscribed_units DESC; shows the unit-count bands to help.")

        cursor.close()
    except Exception as error:
        if conn:
            conn.rollback()
        print(f"[FATAL] Migration 031 failed: {error}")
        raise
    finally:
        if conn:
            conn.close()


if __name__ == '__main__':
    run_migration()
