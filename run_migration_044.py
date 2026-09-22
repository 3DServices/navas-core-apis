#!/usr/bin/env python3
"""Run database migration 044 - geofence presence (server-side alerts).

Creates dll_geozone_presence, where the alert engine remembers whether each
unit is inside each geofence. Nothing is sent for a unit the first time it is
seen, so vehicles already parked inside a zone are not reported as entering it.
"""

import psycopg2
from config import DB_LINK


def run_migration():
    conn = None
    try:
        print("Connecting to database...")
        conn = psycopg2.connect(DB_LINK)
        cur = conn.cursor()
        with open('database/migrations/044_geozone_presence.sql', 'r',
                  encoding='utf-8') as handle:
            cur.execute(handle.read())
        conn.commit()
        print("Migration 044 applied.\n")

        cur.execute("SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'dll_geozone_presence'")
        found = {r[0] for r in cur.fetchall()}
        expected = {'device_imei', 'geozone_uid', 'is_inside',
                    'last_position_ref', 'last_checked'}
        print(f"   {'ok   ' if expected <= found else 'CHECK'} dll_geozone_presence "
              f"({len(found)} columns)")

        cur.execute("SELECT COUNT(*) FROM dll_geozone_presence")
        print(f"   ok    {cur.fetchone()[0]} unit/zone pair(s) tracked so far")

        cur.execute("SELECT COUNT(*) FROM dll_device_events "
                    "WHERE event_condition = 'geofence_breach'")
        print(f"   ok    {cur.fetchone()[0]} geofence rule(s) the engine will check")

        print("\nNext: restart the API, then run one sweep to record where every "
              "unit is before any alert can fire:")
        print("      curl -X POST <api>/alerts/run -H 'X-Service-Key: <key>' "
              "-H 'Content-Type: application/json' -d '{\"data\":{\"live\":true}}'")
        cur.close()
    except Exception as error:
        if conn:
            conn.rollback()
        print(f"[FATAL] Migration 044 failed: {error}")
        raise
    finally:
        if conn:
            conn.close()


if __name__ == '__main__':
    run_migration()
