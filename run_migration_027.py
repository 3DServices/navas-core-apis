#!/usr/bin/env python3
"""Run database migration 027 - Add service_type to abi_products_manager."""

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
        with open('database/migrations/027_add_product_service_type.sql', 'r') as f:
            sql_script = f.read()

        print("Executing migration...")
        cursor.execute(sql_script)
        conn.commit()

        cursor.execute("""
            SELECT column_name, data_type FROM information_schema.columns
            WHERE table_name='abi_products_manager' AND column_name='service_type'
        """)
        print("\nMigration 027 completed:", cursor.fetchall())
        cursor.close()
    except Exception as error:
        if conn:
            conn.rollback()
        print(f"[FATAL] Migration 027 failed: {error}")
        raise
    finally:
        if conn:
            conn.close()


if __name__ == '__main__':
    run_migration()
