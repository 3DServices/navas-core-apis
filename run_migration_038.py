#!/usr/bin/env python3
"""Run database migration 038 - the official product ID register.

Also corrects migration 037's slug expression, which stripped '+' and so
collapsed iVMS onto iVMS+ and OLIWA onto OLIWA+. A database that already ran
037 is fixed by running this; nothing needs re-running.

Loads no data. The register comes from the file:

    python scripts/load_official_product_ids.py database/catalog/Official_Product_IDs_v26.csv
    python scripts/load_official_product_ids.py database/catalog/Official_Product_IDs_v26.csv --commit
    python scripts/load_official_product_ids.py --repair
"""

import psycopg2
from config import DB_LINK

# (input, expected) — '+' must survive, everything else non-alphanumeric goes.
SLUG_PROBES = (
    ('iVMS', 'ivms'),
    ('iVMS+', 'ivms+'),
    ('OLIWA / UKO', 'oliwauko'),
    ('OLIWA+', 'oliwa+'),
    ('MAFTA FLS', 'maftafls'),
    ('  Dash AI ', 'dashai'),
    (None, ''),
)


def run_migration():
    conn = None
    try:
        print("Connecting to database...")
        conn = psycopg2.connect(DB_LINK)
        conn.autocommit = False
        cursor = conn.cursor()

        print("Reading migration file...")
        with open('database/migrations/038_official_product_ids.sql', 'r',
                  encoding='utf-8') as handle:
            cursor.execute(handle.read())
        conn.commit()
        print("Migration 038 applied.\n")

        cursor.execute(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_name = 'abi_official_products'")
        print(f"   {'ok  ' if cursor.fetchone()[0] else 'FAIL'} "
              f"table abi_official_products")

        for view in ('vw_navas_product_repair', 'vw_navas_register_unbuilt',
                     'vw_navas_product_slugs'):
            cursor.execute(
                "SELECT COUNT(*) FROM information_schema.views "
                "WHERE table_name = %s", (view,))
            print(f"   {'ok  ' if cursor.fetchone()[0] else 'FAIL'} view {view}")

        # Optional: needs migration 037's catalogue table.
        cursor.execute(
            "SELECT COUNT(*) FROM information_schema.views "
            "WHERE table_name = 'vw_navas_service_type_sources'")
        if cursor.fetchone()[0]:
            print("   ok   view vw_navas_service_type_sources")
        else:
            print("   --   view vw_navas_service_type_sources skipped "
                  "(migration 037 not run yet; not needed for the repair)")

        # The slug is the whole repair. If it is wrong, products are matched to
        # the wrong register entry and given the wrong code — silently.
        print()
        failures = 0
        for value, expected in SLUG_PROBES:
            cursor.execute("SELECT navas_slug(%s)", (value,))
            got = cursor.fetchone()[0]
            ok = got == expected
            failures += 0 if ok else 1
            print(f"   {'ok  ' if ok else 'FAIL'} navas_slug({value!r}) = {got!r}")
        if failures:
            raise SystemExit(f"{failures} slug probe(s) failed — do not load "
                             f"the register against this.")

        cursor.execute("SELECT COUNT(*) FROM abi_official_products")
        loaded = cursor.fetchone()[0]
        print(f"\n   {loaded} register row(s) loaded so far.")
        if not loaded:
            print("   Next:  python scripts/load_official_product_ids.py "
                  "database/catalog/Official_Product_IDs_v26.csv")

        cursor.close()
    except Exception as error:
        if conn:
            conn.rollback()
        print(f"[FATAL] Migration 038 failed: {error}")
        raise
    finally:
        if conn:
            conn.close()


if __name__ == '__main__':
    run_migration()
