#!/usr/bin/env python3
"""Run database migration 051 - file alerts and geofences by client.

Moves alerts (dll_event_notifications.owner_uid) and geofences
(dll_geozones.geozone_owner) filed under a login's account_uid to that login's
client (account_root), where the fleet summary, the console and the app read
them. The writers already file new rows that way (endpoints/owner_root.py).

This changes existing rows, so by default it only reports what it would move:

    python run_migration_051.py            # dry run: counts, no writes
    python run_migration_051.py --apply    # move the rows

Safe to run again; a second --apply moves nothing.
"""

import sys

import psycopg2
from config import DB_LINK

# What each UPDATE in the .sql would touch, for the dry run.
COUNTS = {
    'alerts': """
        SELECT count(*), count(DISTINCT n.owner_uid)
          FROM dll_event_notifications n
          JOIN dll_access_relay r ON r.account_uid = n.owner_uid
         WHERE COALESCE(r.account_root, '') <> ''
           AND r.account_root <> n.owner_uid""",
    'geofences': """
        SELECT count(*), count(DISTINCT z.geozone_owner)
          FROM dll_geozones z
          JOIN dll_access_relay r ON r.account_uid = z.geozone_owner
         WHERE COALESCE(r.account_root, '') <> ''
           AND r.account_root <> z.geozone_owner""",
    # A moved zone whose name the client already uses ends up as a second
    # zone of that name under the client (zone names are unique per owner
    # only at creation). Listed so they can be renamed.
    'geofence name clashes': """
        SELECT count(*), count(DISTINCT r.account_root)
          FROM dll_geozones z
          JOIN dll_access_relay r ON r.account_uid = z.geozone_owner
          JOIN dll_geozones c ON c.geozone_owner = r.account_root
                              AND LOWER(c.geozone_name) = LOWER(z.geozone_name)
         WHERE COALESCE(r.account_root, '') <> ''
           AND r.account_root <> z.geozone_owner""",
}


def counts(cur):
    out = {}
    for label, sql in COUNTS.items():
        cur.execute(sql)
        out[label] = cur.fetchone()
    return out


def run_migration(apply=False):
    conn = None
    try:
        print("Connecting to database...")
        conn = psycopg2.connect(DB_LINK)
        cur = conn.cursor()
        before = counts(cur)
        for label, (rows, owners) in before.items():
            print(f"   {label:24s} {rows:6d} rows  ({owners} owners)")

        if not apply:
            conn.rollback()
            print("\nDry run: nothing changed. Run with --apply to move the rows.")
            return

        with open('database/migrations/051_file_alerts_by_client.sql', 'r',
                  encoding='utf-8') as handle:
            cur.execute(handle.read())
        after = counts(cur)
        conn.commit()
        print("\nMigration 051 applied.")
        for label in ('alerts', 'geofences'):
            left = after[label][0]
            print(f"   {'ok   ' if left == 0 else 'CHECK'} {label}: {left} still filed under a login")
        cur.close()
    except Exception as error:
        if conn:
            conn.rollback()
        print(f"[FATAL] Migration 051 failed: {error}")
        raise
    finally:
        if conn:
            conn.close()


if __name__ == '__main__':
    run_migration(apply='--apply' in sys.argv[1:])
