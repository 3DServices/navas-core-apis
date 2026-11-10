#!/usr/bin/env python3
"""Run database migration 046 - app guides synced into Waswa's corpus.

Adds dll_waswa_app_guide, which maps each app how-to article (app, slug) to
the newest version uploaded for it, so a sync can tell new, changed and
unchanged articles apart without a person choosing what replaces what.
"""

import psycopg2
from config import DB_LINK


def run_migration():
    conn = None
    try:
        print("Connecting to database...")
        conn = psycopg2.connect(DB_LINK)
        cur = conn.cursor()
        with open('database/migrations/046_waswa_app_guide.sql', 'r',
                  encoding='utf-8') as handle:
            cur.execute(handle.read())
        conn.commit()
        print("Migration 046 applied.\n")

        cur.execute("SELECT COUNT(*) FROM information_schema.tables "
                    "WHERE table_name = 'dll_waswa_app_guide'")
        present = cur.fetchone()[0] == 1
        print(f"   {'ok   ' if present else 'CHECK'} dll_waswa_app_guide present")
        cur.execute("SELECT app, COUNT(*) FROM dll_waswa_app_guide GROUP BY app")
        rows = cur.fetchall()
        print(f"   ok    articles synced so far: "
              f"{', '.join(f'{a}={n}' for a, n in rows) or 'none'}")
        print("\nRestart the API to load the new endpoints.")
        cur.close()
    except Exception as error:
        if conn:
            conn.rollback()
        print(f"[FATAL] Migration 046 failed: {error}")
        raise
    finally:
        if conn:
            conn.close()


if __name__ == '__main__':
    run_migration()
