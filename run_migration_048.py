#!/usr/bin/env python3
"""Run database migration 048 - geozone categories.

Adds geozone_category to dll_geozones (general / depot / customer /
restricted), which PUT /geozones/<geozone_id>/category writes.
"""

import psycopg2
from config import DB_LINK


def run_migration():
    conn = None
    try:
        print("Connecting to database...")
        conn = psycopg2.connect(DB_LINK)
        cur = conn.cursor()
        with open('database/migrations/048_geozone_categories.sql', 'r',
                  encoding='utf-8') as handle:
            cur.execute(handle.read())
        conn.commit()
        print("Migration 048 applied.\n")

        cur.execute("SELECT geozone_category, COUNT(*) FROM dll_geozones "
                    "GROUP BY geozone_category ORDER BY geozone_category")
        for category, count in cur.fetchall():
            print(f"   ok    {category}: {count} geofence(s)")
        print("\nRestart the API to load the new endpoint.")
        cur.close()
    except Exception as error:
        if conn:
            conn.rollback()
        print(f"[FATAL] Migration 048 failed: {error}")
        raise
    finally:
        if conn:
            conn.close()


if __name__ == '__main__':
    run_migration()
