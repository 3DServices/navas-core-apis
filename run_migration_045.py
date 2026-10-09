#!/usr/bin/env python3
"""Run database migration 045 - resources.

Creates dll_resources and dll_resource_items, the one-live-grant index on
dll_object_access, and makes sure the resource staff permissions exist.
"""
import psycopg2
from config import DB_LINK


def run_migration():
    conn = None
    try:
        print("Connecting to database...")
        conn = psycopg2.connect(DB_LINK)
        cur = conn.cursor()
        with open('database/migrations/045_resources.sql', 'r',
                  encoding='utf-8') as handle:
            cur.execute(handle.read())
        conn.commit()
        print("Migration 045 applied.\n")

        for table, expected in (
            ('dll_resources', {'resource_uid', 'account_root', 'resource_name',
                               'resource_description', 'is_deleted'}),
            ('dll_resource_items', {'item_type', 'item_uid', 'resource_uid'}),
        ):
            cur.execute("SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = %s", (table,))
            found = {r[0] for r in cur.fetchall()}
            print(f"   {'ok   ' if expected <= found else 'CHECK'} {table} "
                  f"({len(found)} columns)")

        cur.execute("SELECT 1 FROM pg_indexes WHERE indexname = 'uq_object_access_live'")
        print(f"   {'ok   ' if cur.fetchone() else 'CHECK'} one live grant per user per object")

        cur.execute("SELECT permission_name FROM dll_permissions WHERE permission_name IN "
                    "('can_view_resource_template','can_create_resource_template',"
                    "'can_edit_resource_template','can_share_resource_template')")
        perms = sorted(r[0] for r in cur.fetchall())
        print(f"   {'ok   ' if len(perms) == 4 else 'CHECK'} staff permissions present "
              f"({len(perms)}/4)")

        cur.execute("SELECT COUNT(*) FROM dll_resources WHERE is_deleted = FALSE")
        print(f"   ok    {cur.fetchone()[0]} resource(s) so far")

        print("\nRestart the API to load the resource endpoints.")
        cur.close()
    except Exception as error:
        if conn:
            conn.rollback()
        print(f"[FATAL] Migration 045 failed: {error}")
        raise
    finally:
        if conn:
            conn.close()


if __name__ == '__main__':
    run_migration()
