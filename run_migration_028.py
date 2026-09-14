#!/usr/bin/env python3
"""Run database migration 028 - Seed the official PPMM product catalogue."""

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

        cursor.execute(
            "SELECT service_type, COUNT(*) FROM abi_products_manager "
            "WHERE product_code LIKE '3D-PRD-%' GROUP BY service_type ORDER BY service_type")
        print("\nMigration 028 completed. Seeded catalogue by service type:")
        for row in cursor.fetchall():
            print(f"   - {row[0]}: {row[1]}")
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
