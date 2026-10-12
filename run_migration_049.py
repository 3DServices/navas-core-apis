#!/usr/bin/env python3
"""Run database migration 049 - daily token usage.

Creates dll_token_usage_daily, which POST /tokens/usage/snapshot/run and
GET /tokens/<client_uid>/usage/daily write and read.
"""

import psycopg2
from config import DB_LINK


def run_migration():
    conn = None
    try:
        print("Connecting to database...")
        conn = psycopg2.connect(DB_LINK)
        cur = conn.cursor()
        with open('database/migrations/049_token_usage_daily.sql', 'r',
                  encoding='utf-8') as handle:
            cur.execute(handle.read())
        conn.commit()
        print("Migration 049 applied.\n")

        cur.execute("SELECT to_regclass('dll_token_usage_daily')")
        present = cur.fetchone()[0] is not None
        print(f"   {'ok   ' if present else 'CHECK'} dll_token_usage_daily")
        print("\nRestart the API, then schedule a daily call (close to midnight,")
        print("Africa/Kampala) to POST /tokens/usage/snapshot/run with a staff token.")
        cur.close()
    except Exception as error:
        if conn:
            conn.rollback()
        print(f"[FATAL] Migration 049 failed: {error}")
        raise
    finally:
        if conn:
            conn.close()


if __name__ == '__main__':
    run_migration()
