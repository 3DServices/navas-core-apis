#!/usr/bin/env python3
"""Run database migration 043 - geofence shapes (polygon, circle, line).

Adds geozone_shape, geozone_shape_params and the two colour columns to
dll_geozones. Existing geofences become 'polygon' and keep working as before.
"""

import psycopg2
from config import DB_LINK


def run_migration():
    conn = None
    try:
        print("Connecting to database...")
        conn = psycopg2.connect(DB_LINK)
        cur = conn.cursor()
        with open('database/migrations/043_geozone_shapes.sql', 'r',
                  encoding='utf-8') as handle:
            cur.execute(handle.read())
        conn.commit()
        print("Migration 043 applied.\n")

        cur.execute("SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'dll_geozones' AND column_name IN "
                    "('geozone_shape','geozone_shape_params','geozone_color',"
                    "'geozone_label_color')")
        found = {r[0] for r in cur.fetchall()}
        print(f"   {'ok   ' if len(found) == 4 else 'CHECK'} new geofence columns "
              f"present ({len(found)}/4)")

        cur.execute("SELECT geozone_shape, COUNT(*) FROM dll_geozones "
                    "GROUP BY geozone_shape ORDER BY 1")
        for shape, count in cur.fetchall():
            print(f"   ok    {shape:<8} {count} geofence(s)")
        print("\nRestart the API to load the new geofence shapes.")
        cur.close()
    except Exception as error:
        if conn:
            conn.rollback()
        print(f"[FATAL] Migration 043 failed: {error}")
        raise
    finally:
        if conn:
            conn.close()


if __name__ == '__main__':
    run_migration()
