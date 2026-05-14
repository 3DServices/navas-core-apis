"""
One-time seed script: bootstraps RBAC access for the admin account.

What it does:
  1. Promotes your admin account to 'super_admin' clearance (bypasses all permission checks)
  2. Creates the 'rbac.manage' permission if it doesn't exist
  3. Creates an 'admin' role if none exists, and links rbac.manage to it

Usage:
    python seed_rbac_permission.py
"""

import uuid
import psycopg2
from config import DB_LINK as DB_URL

ACCOUNT_ROOT = "engine"
CREATED_BY = "system"


def main():
    conn = psycopg2.connect(DB_URL)
    try:
        with conn:
            with conn.cursor() as cur:

                # ── Step 1: Show current admin accounts ──────────────────
                print("=== Current admin accounts ===")
                cur.execute(
                    "SELECT account_uid, account_name, username, account_clearance, account_type "
                    "FROM dll_access_relay WHERE access_status = 'active' ORDER BY date_created DESC"
                )
                rows = cur.fetchall()
                for r in rows:
                    print(f"  {r[0][:8]}..  {r[1]:<20} {r[2]:<20} clearance={r[3]:<15} type={r[4]}")

                # ── Step 2: Promote all 'admin' clearance users to 'super_admin' ──
                cur.execute(
                    "UPDATE dll_access_relay SET account_clearance = 'super_admin' "
                    "WHERE account_clearance = 'admin' AND access_status = 'active'"
                )
                promoted = cur.rowcount
                if promoted > 0:
                    print(f"\nPromoted {promoted} account(s) from 'admin' -> 'super_admin'")
                else:
                    print("\nNo accounts with clearance 'admin' found (may already be super_admin)")

                # ── Step 3: Create rbac.manage permission ────────────────
                cur.execute(
                    "SELECT permission_uid FROM dll_permissions "
                    "WHERE permission_name = 'rbac.manage' AND (is_deleted = FALSE OR is_deleted IS NULL)"
                )
                if cur.rowcount > 0:
                    perm_uid = cur.fetchone()[0]
                    print(f"\nPermission 'rbac.manage' already exists: {perm_uid}")
                else:
                    perm_uid = str(uuid.uuid4())
                    cur.execute(
                        "INSERT INTO dll_permissions (permission_uid, permission_name, permission_description, permission_module, account_root, created_by) "
                        "VALUES (%s, %s, %s, %s, %s, %s)",
                        (perm_uid, "rbac.manage", "Full access to RBAC management (roles, permissions, user assignment)", "rbac", ACCOUNT_ROOT, CREATED_BY)
                    )
                    print(f"\nCreated permission 'rbac.manage': {perm_uid}")

                # ── Step 4: Ensure an admin role exists and link the permission ──
                cur.execute(
                    "SELECT role_uid, role_name FROM dll_roles "
                    "WHERE role_name ILIKE '%admin%' AND (is_deleted = FALSE OR is_deleted IS NULL)"
                )
                roles = cur.fetchall()

                if not roles:
                    # Create a super_admin role
                    role_uid = str(uuid.uuid4())
                    cur.execute(
                        "INSERT INTO dll_roles (role_uid, role_name, role_description, account_root, created_by) "
                        "VALUES (%s, %s, %s, %s, %s)",
                        (role_uid, "super_admin", "Full system access", ACCOUNT_ROOT, CREATED_BY)
                    )
                    roles = [(role_uid, "super_admin")]
                    print(f"Created role 'super_admin': {role_uid}")

                for role_uid, role_name in roles:
                    cur.execute(
                        "INSERT INTO dll_role_permissions (role_uid, permission_uid, assigned_by) "
                        "VALUES (%s, %s, %s) ON CONFLICT (role_uid, permission_uid) DO NOTHING",
                        (str(role_uid), str(perm_uid), CREATED_BY)
                    )
                    print(f"Linked 'rbac.manage' -> role '{role_name}' ({role_uid})")

        print("\n=== Done! Your admin account now bypasses permission checks as super_admin. ===")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
