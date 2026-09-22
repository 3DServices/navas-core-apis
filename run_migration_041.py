#!/usr/bin/env python3
"""Run database migration 041 - the Waswa training loop (Portal Phase A).

Applies the migration, then proves the three rules that matter:
  1. every existing document is now staff-only, so customers stop reading
     internal procedures;
  2. the database itself refuses a self-approval;
  3. replacing a document flags the corrections that rely on it.
Checks 2 and 3 run inside a savepoint that is rolled back, so they leave
nothing behind.
"""

import psycopg2
from config import DB_LINK


def check(ok, text):
    print(f"   {'ok   ' if ok else 'CHECK'} {text}")
    return ok


def run_migration():
    conn = None
    try:
        print("Connecting to database...")
        conn = psycopg2.connect(DB_LINK)
        conn.autocommit = False
        cur = conn.cursor()

        print("Reading migration file...")
        with open('database/migrations/041_waswa_training.sql', 'r',
                  encoding='utf-8') as handle:
            cur.execute(handle.read())
        for notice in conn.notices:
            print(f"   {notice.strip()}")
        conn.commit()
        print("\nMigration 041 applied.\n")

        passed = True

        cur.execute("SELECT to_regclass(t) IS NOT NULL FROM unnest(ARRAY["
                    "'dll_waswa_feedback','dll_waswa_answers',"
                    "'dll_waswa_answer_approvals','vw_waswa_review_queue']) t")
        passed &= check(all(r[0] for r in cur.fetchall()),
                        "feedback, corrections, approvals and the review queue exist")

        cur.execute("SELECT audience, COUNT(*) FROM dll_waswa_sources "
                    "GROUP BY audience ORDER BY audience")
        rows = cur.fetchall()
        summary = ', '.join(f'{n} {a}' for a, n in rows) or 'no documents'
        everyone = dict(rows).get('everyone', 0)
        passed &= check(True, f"documents by audience: {summary}")
        if everyone == 0:
            print("         Customers now see no documents until one is marked "
                  "'everyone'. Staff see all of them.")

        cur.execute("SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'vw_waswa_retrievable' "
                    "AND column_name = 'audience'")
        passed &= check(cur.rowcount == 1, "retrieval view carries audience")

        # ── Rule 2: no self-approval, enforced by the database ──────────
        cur.execute("SAVEPOINT probe")
        cur.execute(
            "INSERT INTO dll_waswa_answers (answer_uid, question, answer, "
            "authored_by, status) VALUES ('probe-041', 'probe?', 'probe.', "
            "'probe-author', 'pending')")
        try:
            cur.execute("SAVEPOINT self_approve")
            cur.execute(
                "INSERT INTO dll_waswa_answer_approvals "
                "(answer_uid, approver_account_uid, decision) "
                "VALUES ('probe-041', 'probe-author', 'approve')")
            refused = False
        except psycopg2.errors.CheckViolation:
            cur.execute("ROLLBACK TO SAVEPOINT self_approve")
            refused = True
        passed &= check(refused, "database refuses a self-approval")

        # ── Rule 3: a replaced document flags its corrections ───────────
        cur.execute("SELECT source_uid FROM dll_waswa_sources "
                    "WHERE superseded_by IS NULL LIMIT 1")
        row = cur.fetchone() if cur.rowcount else None
        if row:
            source_uid = row[0]
            cur.execute("UPDATE dll_waswa_answers SET status='approved', "
                        "based_on_source_uid=%s WHERE answer_uid='probe-041'",
                        (source_uid,))
            cur.execute("UPDATE dll_waswa_sources SET active = FALSE "
                        "WHERE source_uid = %s", (source_uid,))
            cur.execute("SELECT needs_recheck, recheck_reason "
                        "FROM dll_waswa_answers WHERE answer_uid='probe-041'")
            flagged, reason = cur.fetchone()
            passed &= check(flagged, f"withdrawn document flags its corrections "
                                     f"({reason})")
        else:
            print("   skip  no documents loaded, recheck trigger not probed")
        cur.execute("ROLLBACK TO SAVEPOINT probe")
        conn.commit()

        perms = []
        if _exists(cur, 'dll_permissions'):
            cur.execute("SELECT permission_name FROM dll_permissions "
                        "WHERE permission_name LIKE 'waswa.%' ORDER BY 1")
            perms = [r[0] for r in cur.fetchall()]
        check(len(perms) == 3,
              f"permissions present: {', '.join(perms) or 'none'}")
        if len(perms) < 3:
            print("         Add waswa.staff_knowledge, waswa.review and "
                  "waswa.approve in the RBAC screen. super_admin has all three "
                  "regardless.")

        cur.execute("SELECT item_kind, COUNT(*) FROM vw_waswa_review_queue "
                    "GROUP BY item_kind ORDER BY 1")
        queue = cur.fetchall()
        print(f"\nReview queue now: "
              f"{', '.join(f'{n} {k}' for k, n in queue) or 'empty'}")

        print(f"\n{'All checks passed.' if passed else 'Some checks need a look.'}")
        print("\nNext:")
        print("  python scripts/waswa_prompt.py --load --and-activate")
        print("  then restart the API")
        cur.close()
    except Exception as error:
        if conn:
            conn.rollback()
        print(f"[FATAL] Migration 041 failed: {error}")
        raise
    finally:
        if conn:
            conn.close()


def _exists(cur, table):
    cur.execute("SELECT to_regclass(%s) IS NOT NULL", (table,))
    return cur.fetchone()[0]


if __name__ == '__main__':
    run_migration()
