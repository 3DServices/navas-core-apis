#!/usr/bin/env python3
"""Run database migration 034 - the navas_num() text-to-number helper."""

import psycopg2
from config import DB_LINK

PROBES = (
    ("'500'", 500),
    ("'1,200.5'", 1200.5),
    ("' 42 '", 42),
    ("'0'", 0),
    ("'units_unfined_waiting_for_first_use'", None),
    ("'column deprecated use token_units_left column'", None),
    ("''", None),
    ("NULL", None),
)


def run_migration():
    conn = None
    try:
        print("Connecting to database...")
        conn = psycopg2.connect(DB_LINK)
        conn.autocommit = False
        cursor = conn.cursor()

        print("Reading migration file...")
        with open('database/migrations/034_navas_num_helper.sql', 'r') as f:
            cursor.execute(f.read())
        conn.commit()

        print("\nMigration 034 completed. navas_num() behaviour:")
        failures = 0
        for literal, expected in PROBES:
            cursor.execute(f"SELECT navas_num({literal})")
            got = cursor.fetchone()[0]
            got = float(got) if got is not None else None
            ok = (got == expected) if expected is not None else (got is None)
            failures += 0 if ok else 1
            print(f"   {'ok  ' if ok else 'FAIL'} navas_num({literal}) = {got}")

        if failures:
            raise SystemExit(f"{failures} probe(s) failed — do not deploy this.")

        # How much of the live data this actually affects.
        cursor.execute("""
            SELECT COUNT(*),
                   COUNT(*) FILTER (WHERE navas_num(token_units_left) IS NOT NULL),
                   COUNT(*) FILTER (WHERE navas_num(token_hours_left) IS NOT NULL)
            FROM dll_user_token_accounts
        """)
        total, units_readable, hours_readable = cursor.fetchone()
        print(f"\n   dll_user_token_accounts: {total} rows")
        print(f"      token_units_left readable as a number: {units_readable}")
        print(f"      token_hours_left readable as a number: {hours_readable}")
        if total and not hours_readable:
            print("      (expected — token_hours_* is deprecated and holds a notice)")

        cursor.close()
    except Exception as error:
        if conn:
            conn.rollback()
        print(f"[FATAL] Migration 034 failed: {error}")
        raise
    finally:
        if conn:
            conn.close()


if __name__ == '__main__':
    run_migration()
