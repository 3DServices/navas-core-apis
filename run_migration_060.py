#!/usr/bin/env python3
"""Run database migration 060 - the driver an alert is about.

Adds driver_uid and driver_name to dll_event_notifications, and an index for
"alerts about this driver". Changes no existing row. Safe to run again.

The alert engine starts filling the columns on its next sweep after this; a
running server notices them within one sweep (alert_engine._driver_columns).
"""

import psycopg2
from config import DB_LINK


def run_migration():
    conn = None
    try:
        print("Connecting to database...")
        conn = psycopg2.connect(DB_LINK)
        cur = conn.cursor()
        with open('database/migrations/060_alert_driver.sql', 'r',
                  encoding='utf-8') as handle:
            cur.execute(handle.read())
        conn.commit()
        print("Migration 060 applied.\n")

        cur.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'dll_event_notifications' "
            "AND column_name IN ('driver_uid', 'driver_name')")
        cols = {r[0] for r in cur.fetchall()}
        cur.execute("SELECT to_regclass('idx_event_notifications_driver')")
        index = cur.fetchone()[0] is not None
        for col in ('driver_uid', 'driver_name'):
            print(f"   {'ok   ' if col in cols else 'CHECK'} dll_event_notifications.{col}")
        print(f"   {'ok   ' if index else 'CHECK'} idx_event_notifications_driver")
        cur.close()
    except Exception as error:
        if conn:
            conn.rollback()
        print(f"Migration 060 failed: {error}")
        raise
    finally:
        if conn:
            conn.close()


if __name__ == '__main__':
    run_migration()
