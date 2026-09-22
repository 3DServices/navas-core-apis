#!/usr/bin/env python3
"""Run database migration 039 - OLIWA (Uganda) and UKO (Kenya) as one product.

Reports what it changed and, more importantly, confirms that the eleven
genuine duplicate-product rows are STILL blocked. The whole point of this
migration is to let one registered product have a row per country; if that
relaxation also let the accidental duplicates through, it would have quietly
undone the guard that protects them.
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
            "SELECT verdict, COUNT(*) FROM vw_navas_product_repair "
            "GROUP BY verdict")
        before = dict(cursor.fetchall()) if cursor.rowcount > 0 else {}

        print("Reading migration file...")
        with open('database/migrations/039_country_brands.sql', 'r',
                  encoding='utf-8') as handle:
            cursor.execute(handle.read())
        conn.commit()
        print("Migration 039 applied.\n")

        cursor.execute(
            "SELECT product_name, country_scope, product_code "
            "FROM abi_products_manager "
            "WHERE navas_slug(product_name) IN ('oliwa','uko','oliwaplus','oliwa+') "
            "ORDER BY product_name")
        rows = cursor.fetchall() if cursor.rowcount > 0 else []
        print(f"{'product':<16} {'country':<10} code")
        for name, country, code in rows:
            print(f"{name:<16} {(country or '-'):<10} {code or '(empty)'}")

        # Named by product, because each of the two rows legitimately gets both
        # brand names — a bare list looks like every alias was inserted twice.
        cursor.execute(
            "SELECT p.product_name, a.alias, a.country_scope "
            "FROM abi_product_aliases a "
            "JOIN abi_products_manager p ON p.product_uid = a.product_uid "
            "WHERE a.alias_kind IN ('country_brand','register_name') "
            "ORDER BY p.product_name, a.alias, a.country_scope")
        aliases = cursor.fetchall() if cursor.rowcount > 0 else []
        print(f"\n{len(aliases)} country/register alias(es) seeded:")
        for product, alias, country in aliases:
            print(f"   {product:<12} is also known as {alias:<14} "
                  f"in {country or 'all countries'}")

        cursor.execute(
            "SELECT verdict, COUNT(*) FROM vw_navas_product_repair "
            "GROUP BY verdict ORDER BY COUNT(*) DESC")
        after = dict(cursor.fetchall()) if cursor.rowcount > 0 else {}
        print(f"\n{'before':>7} {'after':>6}  verdict")
        for verdict in sorted(set(before) | set(after)):
            print(f"{before.get(verdict, 0):>7} {after.get(verdict, 0):>6}  {verdict}")

        # The guard that must survive this change.
        merges = after.get('MERGE: another row already holds this code', 0)
        warning = ('' if merges == 11 else
                   ' — expected 11; read the list before running the repair')
        print(f"\n   {'ok  ' if merges == 11 else 'CHECK'} {merges} row(s) still "
              f"blocked as duplicate products{warning}")

        cursor.execute("SELECT product_id, registered_as, product_rows, countries "
                       "FROM vw_navas_country_variants")
        variants = cursor.fetchall() if cursor.rowcount > 0 else []
        if variants:
            print(f"\nRegistered products backed by more than one row:")
            for code, name, count, countries in variants:
                print(f"   {code:<12} {name[:22]:22} {count} row(s)  [{countries}]")
            print("   Different countries here is the intended shape. "
                  "'(no country)' twice is a duplicate.")

        print("\nNext:  python scripts/load_official_product_ids.py --repair")
        cursor.close()
    except Exception as error:
        if conn:
            conn.rollback()
        print(f"[FATAL] Migration 039 failed: {error}")
        raise
    finally:
        if conn:
            conn.close()


if __name__ == '__main__':
    run_migration()
