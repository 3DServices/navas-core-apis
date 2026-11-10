#!/usr/bin/env python3
"""Run database migration 047 - alert acknowledgement.

Adds acknowledged_at, acknowledged_by and acknowledge_note to
dll_event_notifications, which PUT /notifications/<uid>/acknowledge writes.
"""

import psycopg2
from config import DB_LINK


def run_migration():
    conn = None
    try:
        print("Connecting to database...")
        conn = psycopg2.connect(DB_LINK)
        cur = conn.cursor()
        with open('database/migrations/047_alert_acknowledgement.sql', 'r',
                  encoding='utf-8') as handle:
            cur.execute(handle.read())
        conn.commit()
        print("Migration 047 applied.\n")

        cur.execute("SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'dll_event_notifications' AND column_name "
                    "IN ('acknowledged_at', 'acknowledged_by', 'acknowledge_note')")
        present = {row[0] for row in cur.fetchall()}
        for column in ('acknowledged_at', 'acknowledged_by', 'acknowledge_note'):
            print(f"   {'ok   ' if column in present else 'CHECK'} "
                  f"dll_event_notifications.{column}")
        cur.execute("SELECT COUNT(*) FROM dll_event_notifications "
                    "WHERE acknowledged_at IS NULL")
        print(f"   ok    open (unacknowledged) alerts: {cur.fetchone()[0]}")
        print("\nRestart the API to load the new endpoint.")
        cur.close()
    except Exception as error:
        if conn:
            conn.rollback()
        print(f"[FATAL] Migration 047 failed: {error}")
        raise
    finally:
        if conn:
            conn.close()


if __name__ == '__main__':
    run_migration()
