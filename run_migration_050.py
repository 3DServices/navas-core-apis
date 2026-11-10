#!/usr/bin/env python3
"""Run database migration 050 - referrals (Refer & Earn).

Creates dll_referral_codes and dll_referrals, which the /referrals routes and
the mobile-money payment webhook read and write.
"""

import psycopg2
from config import DB_LINK


def run_migration():
    conn = None
    try:
        print("Connecting to database...")
        conn = psycopg2.connect(DB_LINK)
        cur = conn.cursor()
        with open('database/migrations/050_referrals.sql', 'r',
                  encoding='utf-8') as handle:
            cur.execute(handle.read())
        conn.commit()
        print("Migration 050 applied.\n")

        for table in ('dll_referral_codes', 'dll_referrals'):
            cur.execute("SELECT to_regclass(%s)", (table,))
            present = cur.fetchone()[0] is not None
            print(f"   {'ok   ' if present else 'CHECK'} {table}")
        print("\nSet REFERRAL_REWARD_TOKEN_ID to the token_id of a 24-hour token")
        print("in dll_tokens_registry, then restart the API. Until then rewards")
        print("are held as 'qualified' and can be paid from")
        print("POST /referrals/admin/<id>/reward.")
        cur.close()
    except Exception as error:
        if conn:
            conn.rollback()
        print(f"[FATAL] Migration 050 failed: {error}")
        raise
    finally:
        if conn:
            conn.close()


if __name__ == '__main__':
    run_migration()
