#!/usr/bin/env python3
"""Run database migration 054 - alert rule state.

Creates dll_alert_rule_state and dll_alert_unit_cursor, which the alert engine
(endpoints/alert_engine.py) uses to check speed, ignition and offline rules.
Only creates; changes no existing row. Safe to run again.
"""

import psycopg2
from config import DB_LINK


def run_migration():
    conn = None
    try:
        print("Connecting to database...")
        conn = psycopg2.connect(DB_LINK)
        cur = conn.cursor()
        with open('database/migrations/054_alert_rule_state.sql', 'r',
                  encoding='utf-8') as handle:
            cur.execute(handle.read())
        conn.commit()
        print("Migration 054 applied.\n")

        for table in ('dll_alert_rule_state', 'dll_alert_unit_cursor'):
            cur.execute("SELECT to_regclass(%s)", (table,))
            present = cur.fetchone()[0] is not None
            print(f"   {'ok   ' if present else 'CHECK'} {table}")
        cur.close()
    except Exception as error:
        if conn:
            conn.rollback()
        print(f"[FATAL] Migration 054 failed: {error}")
        raise
    finally:
        if conn:
            conn.close()


if __name__ == '__main__':
    run_migration()
