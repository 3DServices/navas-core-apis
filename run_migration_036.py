#!/usr/bin/env python3
"""Run database migration 036 - repair the product aliases 032 never seeded.

Reports what it actually inserted, per alias, because the whole reason this
migration exists is that its predecessor inserted nothing and said nothing.
A migration that can silently do no work has to be made to prove it did some.
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

        cursor.execute("SELECT COUNT(*) FROM abi_product_aliases")
        before = cursor.fetchone()[0]
        print(f"Aliases before: {before}")

        print("Reading migration file...")
        with open('database/migrations/036_fix_product_aliases.sql', 'r',
                  encoding='utf-8') as handle:
            cursor.execute(handle.read())
        conn.commit()

        cursor.execute("SELECT COUNT(*) FROM abi_product_aliases")
        after = cursor.fetchone()[0]
        print(f"Aliases after:  {after}   ({after - before:+d})\n")

        cursor.execute(
            "SELECT a.alias, p.product_name, a.source_ref "
            "FROM abi_product_aliases a "
            "LEFT JOIN abi_products_manager p ON p.product_uid = a.product_uid "
            "ORDER BY a.alias")
        rows = cursor.fetchall() if cursor.rowcount > 0 else []
        if rows:
            print(f"{'alias':<22} {'resolves to':<26} source")
            for alias, name, source in rows:
                print(f"{alias:<22} {(name or '(orphaned)'):<26} "
                      f"{(source or '')[:44]}")
        else:
            print("Still no aliases. That means abi_products_manager holds no "
                  "product whose name matches MAFTA%, 'OLIWA / UKO', 'OLIWA+' "
                  "or 'iVMS+' in any casing. Check what the names actually are:")
            cursor.execute(
                "SELECT product_name FROM abi_products_manager "
                "WHERE product_name ILIKE '%maf%' OR product_name ILIKE '%oliwa%' "
                "   OR product_name ILIKE '%uko%'  OR product_name ILIKE '%ivms%' "
                "ORDER BY product_name")
            for (name,) in cursor.fetchall():
                print(f"   {name!r}")

        # Re-running must be a no-op now, not a doubling. Prove it.
        with open('database/migrations/036_fix_product_aliases.sql', 'r',
                  encoding='utf-8') as handle:
            cursor.execute(handle.read())
        conn.commit()
        cursor.execute("SELECT COUNT(*) FROM abi_product_aliases")
        again = cursor.fetchone()[0]
        print(f"\n   {'ok  ' if again == after else 'FAIL'} re-running the "
              f"migration changed nothing ({after} -> {again})")

        cursor.close()
    except Exception as error:
        if conn:
            conn.rollback()
        print(f"[FATAL] Migration 036 failed: {error}")
        raise
    finally:
        if conn:
            conn.close()


if __name__ == '__main__':
    run_migration()
