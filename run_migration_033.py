#!/usr/bin/env python3
"""Run database migration 033 - Waswa gated actions and their approvers."""

import psycopg2
from config import DB_LINK


def run_migration():
    conn = None
    try:
        print("Connecting to database...")
        conn = psycopg2.connect(DB_LINK)
        conn.autocommit = False
        cursor = conn.cursor()

        print("Reading migration file...")
        with open('database/migrations/033_waswa_gated_actions.sql', 'r') as f:
            sql_script = f.read()

        print("Executing migration...")
        cursor.execute(sql_script)
        conn.commit()

        cursor.execute("""
            SELECT COALESCE(approval_level::text, 'unassigned') AS level,
                   COUNT(*)
            FROM dll_waswa_gated_actions
            GROUP BY 1 ORDER BY 1
        """)
        print("\nMigration 033 completed. Gated actions by approval level:")
        for level, count in cursor.fetchall():
            label = {
                '0': '0 — automated (Waswa may act)',
                '1': '1 — sales staff',
                '2': '2 — sales manager / CSO / customer success',
                '3': '3 — CEO',
            }.get(level, 'unassigned — no approver named')
            print(f"   {label:46} {count:3}")

        cursor.execute("SELECT COUNT(*) FROM vw_waswa_unassigned_approvals")
        gaps = cursor.fetchone()[0]
        if gaps:
            print(f"\n   {gaps} actions still need a business decision:")
            cursor.execute(
                "SELECT action_key, approver_gap, threshold_gap "
                "FROM vw_waswa_unassigned_approvals ORDER BY action_key")
            for action, approver_gap, threshold_gap in cursor.fetchall():
                gap = ' + '.join(g for g in (approver_gap, threshold_gap) if g)
                print(f"      - {action:34} {gap}")
            print("\n   Until these are filled in, Waswa proposes and waits;")
            print("   it never acts on any of them.")

        cursor.close()
    except Exception as error:
        if conn:
            conn.rollback()
        print(f"[FATAL] Migration 033 failed: {error}")
        raise
    finally:
        if conn:
            conn.close()


if __name__ == '__main__':
    run_migration()
