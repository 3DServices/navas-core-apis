#!/usr/bin/env python3
"""Run database migration 028 - Seed the PPMM add-on apps catalogue."""

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
        with open('database/migrations/028_seed_ppmm_catalog.sql', 'r') as f:
            sql_script = f.read()

        print("Executing migration...")
        cursor.execute(sql_script)
        conn.commit()

        cursor.execute("""
            SELECT product_uid, product_name, service_type
            FROM abi_products_manager
            WHERE service_type ILIKE '%add-on%'
            ORDER BY product_name
        """)
        rows = cursor.fetchall()
        print(f"\nMigration 028 completed. {len(rows)} add-on products seeded:")
        for r in rows:
            print(f"   - {r[0]:<12} {r[1]:<16} ({r[2]})")
        cursor.close()
    except Exception as error:
        if conn:
            conn.rollback()
        print(f"[FATAL] Migration 028 failed: {error}")
        raise
    finally:
        if conn:
            conn.close()


if __name__ == '__main__':
    run_migration()
