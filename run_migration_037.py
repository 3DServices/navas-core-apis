#!/usr/bin/env python3
"""Run database migration 037 - the approved catalogue object universe.

Creates the table and the reconciliation views. It loads nothing: the objects
come from the workbook, via

    python scripts/load_navas_catalog.py NAVAS_CATALOG_v26.03.30.xlsx
    python scripts/load_navas_catalog.py NAVAS_CATALOG_v26.03.30.xlsx --commit
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

        print("Reading migration file...")
        with open('database/migrations/037_navas_catalog_objects.sql', 'r',
                  encoding='utf-8') as handle:
            cursor.execute(handle.read())
        conn.commit()
        print("Migration 037 applied.\n")

        cursor.execute(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_name = 'abi_catalog_objects'")
        print(f"   {'ok  ' if cursor.fetchone()[0] else 'FAIL'} "
              f"table abi_catalog_objects")

        for view in ('vw_navas_catalog_reconciliation',
                     'vw_navas_service_types',
                     'vw_navas_service_type_drift'):
            cursor.execute(
                "SELECT COUNT(*) FROM information_schema.views "
                "WHERE table_name = %s", (view,))
            print(f"   {'ok  ' if cursor.fetchone()[0] else 'FAIL'} view {view}")

        # The reconciliation view must run even with the catalogue empty —
        # that is its first and most useful state, listing every product row as
        # unapproved rather than raising.
        cursor.execute("SELECT COUNT(*) FROM vw_navas_catalog_reconciliation")
        rows = cursor.fetchone()[0]
        print(f"   ok   reconciliation view runs against an empty catalogue "
              f"({rows} row(s))")

        cursor.execute("SELECT COUNT(*) FROM abi_catalog_objects")
        loaded = cursor.fetchone()[0]
        print(f"\n   {loaded} catalogue object(s) loaded so far.")
        if not loaded:
            print("   Next:  python scripts/load_navas_catalog.py "
                  "<NAVAS_CATALOG_*.xlsx>")

        cursor.close()
    except Exception as error:
        if conn:
            conn.rollback()
        print(f"[FATAL] Migration 037 failed: {error}")
        raise
    finally:
        if conn:
            conn.close()


if __name__ == '__main__':
    run_migration()
