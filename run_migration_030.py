#!/usr/bin/env python3
"""Run database migration 030 - Waswa AI Phase 1 foundation tables."""

import psycopg2
from config import DB_LINK

TABLES = (
    'dll_waswa_prompts',
    'dll_waswa_conversations',
    'dll_waswa_messages',
    'dll_waswa_evidence',
    'dll_waswa_offers',
    'dll_waswa_transparency_log',
)


def run_migration():
    conn = None
    try:
        print("Connecting to database...")
        conn = psycopg2.connect(DB_LINK)
        conn.autocommit = False
        cursor = conn.cursor()

        print("Reading migration file...")
        with open('database/migrations/030_waswa_foundation.sql', 'r') as f:
            sql_script = f.read()

        print("Executing migration...")
        cursor.execute(sql_script)
        conn.commit()

        print("\nMigration 030 completed. Tables created:")
        for table in TABLES:
            cursor.execute("""
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_name = %s
                ORDER BY ordinal_position
            """, (table,))
            cols = cursor.fetchall()
            print(f"\n   {table} ({len(cols)} columns)")
            for c in cols:
                print(f"      - {c[0]} ({c[1]})")

        cursor.execute(
            "SELECT version, is_active FROM dll_waswa_prompts "
            "WHERE prompt_key = 'runtime_system' ORDER BY version"
        )
        prompts = cursor.fetchall()
        print("\n   runtime_system prompt versions:")
        for version, active in prompts:
            print(f"      - v{version}{' (active)' if active else ''}")

        cursor.close()
    except Exception as error:
        if conn:
            conn.rollback()
        print(f"[FATAL] Migration 030 failed: {error}")
        raise
    finally:
        if conn:
            conn.close()


if __name__ == '__main__':
    run_migration()
