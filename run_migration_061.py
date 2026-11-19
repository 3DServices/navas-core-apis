#!/usr/bin/env python3
"""Run database migration 061 - driver scoring rules per client.

Creates dll_driver_score_configs if missing, and adds client_uid,
max_deduction, created_at, updated_at and a one-rule-per-violation-per-client
index. Changes no existing row. Safe to run again.

Until it runs, scorecards still work: every client is scored by the built-in
default rules (endpoints/driver_scoring.py), and saving rules is refused.
"""

import psycopg2
from config import DB_LINK


def run_migration():
    conn = None
    try:
        print("Connecting to database...")
        conn = psycopg2.connect(DB_LINK)
        cur = conn.cursor()
        with open('database/migrations/061_driver_scoring.sql', 'r',
                  encoding='utf-8') as handle:
            cur.execute(handle.read())
        conn.commit()
        print("Migration 061 applied.\n")

        cur.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'dll_driver_score_configs' "
            "AND column_name IN ('client_uid', 'max_deduction', 'created_at', 'updated_at')")
        cols = {r[0] for r in cur.fetchall()}
        cur.execute("SELECT to_regclass('uq_driver_score_client_violation')")
        index = cur.fetchone()[0] is not None
        for col in ('client_uid', 'max_deduction', 'created_at', 'updated_at'):
            print(f"   {'ok   ' if col in cols else 'CHECK'} dll_driver_score_configs.{col}")
        print(f"   {'ok   ' if index else 'CHECK'} uq_driver_score_client_violation")
        cur.execute("SELECT COUNT(*) FROM dll_driver_score_configs WHERE client_uid IS NULL")
        print(f"\n   {cur.fetchone()[0]} older rule(s) with no client: kept, not used.")
        cur.close()
    except Exception as error:
        if conn:
            conn.rollback()
        print(f"Migration 061 failed: {error}")
        raise
    finally:
        if conn:
            conn.close()


if __name__ == '__main__':
    run_migration()
