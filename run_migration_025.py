#!/usr/bin/env python3
"""Run database migration 025 - Auto top-up settings columns on dll_auto_renew_settings."""

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
        with open('database/migrations/025_auto_renew_topup.sql', 'r') as f:
            sql_script = f.read()

        print("Executing migration...")
        cursor.execute(sql_script)
        conn.commit()

        cursor.execute("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'dll_auto_renew_settings'
              AND column_name IN ('top_up_enabled','top_up_token_uid','top_up_quantity',
                                  'momo_number','daily_topup_limit','channels',
                                  'consent_at','last_topup_at')
            ORDER BY column_name
        """)
        print("\nMigration 025 completed. New auto-renew settings columns:")
        for c in cursor.fetchall():
            print(f"   - {c[0]} ({c[1]})")
        cursor.close()
    except Exception as error:
        if conn:
            conn.rollback()
        print(f"[FATAL] Migration 025 failed: {error}")
        raise
    finally:
        if conn:
            conn.close()


if __name__ == '__main__':
    run_migration()
