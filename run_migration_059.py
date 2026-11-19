#!/usr/bin/env python3
"""Run database migration 059 - token SKU + eShop description.

Adds token_sku and token_description to dll_tokens_registry, plus a unique
index on (token_sku, currency). Changes no existing row. Safe to run again.

Run this before scripts/seed_tokens_oliwa_veba.py.
"""

import psycopg2
from config import DB_LINK


def run_migration():
    conn = None
    try:
        print("Connecting to database...")
        conn = psycopg2.connect(DB_LINK)
        cur = conn.cursor()
        with open('database/migrations/059_token_sku_description.sql', 'r',
                  encoding='utf-8') as handle:
            cur.execute(handle.read())
        conn.commit()
        print("Migration 059 applied.\n")

        cur.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'dll_tokens_registry' "
            "AND column_name IN ('token_sku', 'token_description')"
        )
        cols = {r[0] for r in cur.fetchall()}
        cur.execute("SELECT to_regclass('uq_tokens_registry_sku_currency')")
        index = cur.fetchone()[0] is not None
        for col in ('token_sku', 'token_description'):
            print(f"   {'ok   ' if col in cols else 'CHECK'} dll_tokens_registry.{col}")
        print(f"   {'ok   ' if index else 'CHECK'} uq_tokens_registry_sku_currency")
        cur.close()
    except Exception as error:
        if conn:
            conn.rollback()
        print(f"Migration 059 failed: {error}")
        raise
    finally:
        if conn:
            conn.close()


if __name__ == '__main__':
    run_migration()
