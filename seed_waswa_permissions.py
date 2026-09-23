"""
One-time seed: adds the Waswa AI permissions to RBAC under the 'waswa' module.

    waswa.staff_knowledge  Waswa may answer this person from staff-only
                           documents and corrections.
    waswa.review           See the Waswa console, conversations and review
                           queue; write corrections; upload documents.
    waswa.approve          Approve or reject corrections and documents;
                           remove, restore and edit documents.

It only creates the permissions. It does not give them to any role: choose
who gets them in the CMS under RBAC -> Roles -> Edit role -> "waswa".

Super admins, and admins on internal (non-customer) accounts, already have
all three without being assigned them. Customer accounts never get them,
even if they are ticked on a role a customer admin shares.

Safe to run more than once.

Usage:
    python seed_waswa_permissions.py
"""

import uuid
import psycopg2
from config import DB_LINK as DB_URL

ACCOUNT_ROOT = "engine"
CREATED_BY = "system"
MODULE = "waswa"

PERMISSIONS = [
    ("waswa.staff_knowledge",
     "Waswa may answer this person from staff-only documents and corrections"),
    ("waswa.review",
     "Open the Waswa AI Console: conversations, review queue, write corrections, upload documents"),
    ("waswa.approve",
     "Approve or reject Waswa corrections and documents; remove, restore and edit documents"),
]


def main():
    conn = psycopg2.connect(DB_URL)
    try:
        with conn:
            with conn.cursor() as cur:
                for name, description in PERMISSIONS:
                    cur.execute(
                        "SELECT permission_uid, permission_module FROM dll_permissions "
                        "WHERE permission_name = %s AND (is_deleted = FALSE OR is_deleted IS NULL)",
                        (name,))
                    row = cur.fetchone()
                    if row:
                        if row[1] != MODULE:
                            cur.execute(
                                "UPDATE dll_permissions SET permission_module = %s "
                                "WHERE permission_uid = %s", (MODULE, row[0]))
                            print(f"  {name:<24} already existed; moved to module '{MODULE}'")
                        else:
                            print(f"  {name:<24} already exists")
                        continue
                    cur.execute(
                        "INSERT INTO dll_permissions (permission_uid, permission_name, "
                        "permission_description, permission_module, account_root, created_by) "
                        "VALUES (%s, %s, %s, %s, %s, %s)",
                        (str(uuid.uuid4()), name, description, MODULE, ACCOUNT_ROOT, CREATED_BY))
                    print(f"  {name:<24} created")

                cur.execute(
                    "SELECT role_name FROM dll_roles "
                    "WHERE is_deleted = FALSE OR is_deleted IS NULL ORDER BY role_name")
                roles = [r[0] for r in cur.fetchall()]
        print("\nDone. Assign them in the CMS: RBAC -> Roles -> Edit role -> 'waswa'.")
        print("Existing roles: " + (", ".join(roles) or "(none)"))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
