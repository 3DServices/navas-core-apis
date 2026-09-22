#!/usr/bin/env python3
"""Run database migration 032 - PPMM product attributes and child tables."""

import psycopg2
from config import DB_LINK

CHILD_TABLES = (
    'abi_product_aliases',
    'abi_product_capabilities',
    'abi_product_hardware',
    'abi_product_segments',
)


def run_migration():
    conn = None
    try:
        print("Connecting to database...")
        conn = psycopg2.connect(DB_LINK)
        conn.autocommit = False
        cursor = conn.cursor()

        print("Reading migration file...")
        with open('database/migrations/032_ppmm_product_attributes.sql', 'r') as f:
            sql_script = f.read()

        print("Executing migration...")
        cursor.execute(sql_script)
        conn.commit()

        cursor.execute("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'abi_products_manager'
            ORDER BY ordinal_position
        """)
        print("\nMigration 032 completed. abi_products_manager columns:")
        for name, dtype in cursor.fetchall():
            print(f"   - {name} ({dtype})")

        print("\nChild tables:")
        for table in CHILD_TABLES:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            print(f"   - {table}: {cursor.fetchone()[0]} rows")

        cursor.execute(
            "SELECT a.alias, p.product_name FROM abi_product_aliases a "
            "JOIN abi_products_manager p ON p.product_uid = a.product_uid "
            "ORDER BY a.alias"
        )
        aliases = cursor.fetchall()
        if aliases:
            print("\nSeeded aliases:")
            for alias, product in aliases:
                print(f"   - {alias} -> {product}")

        cursor.execute("""
            SELECT COUNT(*) FROM abi_products_manager
            WHERE attributes_loaded_at IS NOT NULL
        """)
        loaded = cursor.fetchone()[0]
        print(f"\n   {loaded} products have attributes loaded.")
        if loaded == 0:
            print("   Expected — the columns are empty until you run:")
            print("     python scripts/load_ppmm_attributes.py <ppmm_export.csv>")
            print("   Until then Waswa can name products and say what it does")
            print("   not know, but cannot answer capability questions.")

        cursor.close()
    except Exception as error:
        if conn:
            conn.rollback()
        print(f"[FATAL] Migration 032 failed: {error}")
        raise
    finally:
        if conn:
            conn.close()


if __name__ == '__main__':
    run_migration()
