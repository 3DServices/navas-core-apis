#!/usr/bin/env python3
"""Run database migration 040 - let an alias name more than one product row.

Prints the NOTICEs the migration raises, because the useful information here is
which constraint it found and dropped — the bug it fixes was invisible exactly
because a failed insert said nothing.
"""

import psycopg2
from config import DB_LINK


def run_migration():
    conn = None
    try:
        print("Connecting to database...")
        conn = psycopg2.connect(DB_LINK)
        conn.autocommit = False
        cursor = conn.cursor()

        cursor.execute(
            "SELECT i.indexrelid::regclass::text, i.indisunique, i.indnatts "
            "FROM pg_index i "
            "WHERE i.indrelid = 'abi_product_aliases'::regclass AND i.indisunique")
        print("Unique indexes on abi_product_aliases before:")
        for name, _unique, cols in cursor.fetchall():
            print(f"   {name}  ({cols} column(s))")

        print("\nReading migration file...")
        with open('database/migrations/040_alias_uniqueness.sql', 'r',
                  encoding='utf-8') as handle:
            cursor.execute(handle.read())
        for notice in conn.notices:
            print(f"   {notice.strip()}")
        conn.commit()
        print("\nMigration 040 applied.\n")

        cursor.execute(
            "SELECT p.product_name, p.country_scope, a.alias, a.country_scope "
            "FROM abi_product_aliases a "
            "JOIN abi_products_manager p ON p.product_uid = a.product_uid "
            "WHERE navas_slug(p.product_name) IN ('oliwa','uko') "
            "ORDER BY p.product_name, a.alias")
        rows = cursor.fetchall() if cursor.rowcount > 0 else []
        print(f"{'product':<10} {'country':<9} {'alias':<14} used in")
        for product, pcountry, alias, acountry in rows:
            print(f"{product:<10} {(pcountry or '-'):<9} {alias:<14} "
                  f"{acountry or 'all countries'}")

        expected = 4       # OLIWA, UKO, and 'OLIWA / UKO' on each of two rows
        print(f"\n   {'ok  ' if len(rows) == expected else 'CHECK'} "
              f"{len(rows)} alias row(s) across oliwa and uko "
              f"(expected {expected})")

        cursor.execute(
            "SELECT product_name, verdict FROM vw_navas_product_repair "
            "WHERE navas_slug(product_name) IN ('oliwa','uko') "
            "ORDER BY product_name")
        for name, verdict in cursor.fetchall():
            print(f"   {name:<10} {verdict}")

        cursor.execute(
            "SELECT verdict, COUNT(*) FROM vw_navas_product_repair "
            "GROUP BY verdict ORDER BY COUNT(*) DESC")
        print(f"\n{'count':>6}  verdict")
        for verdict, count in cursor.fetchall():
            print(f"{count:>6}  {verdict}")

        print("\nNext:  python scripts/load_official_product_ids.py --repair")
        cursor.close()
    except Exception as error:
        if conn:
            conn.rollback()
        print(f"[FATAL] Migration 040 failed: {error}")
        raise
    finally:
        if conn:
            conn.close()


if __name__ == '__main__':
    run_migration()
