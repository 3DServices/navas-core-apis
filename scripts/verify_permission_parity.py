#!/usr/bin/env python3
"""
verify_permission_parity.py -- does the one-query permission loader return
EXACTLY what the three-query one did, for every real account?

WHY THIS EXISTS

_load_user_permissions is the access guard's lookup. It decides, on every
authenticated request in the application, what a caller is allowed to do. It
used to run three sequential queries -- account row, then role_uid, then
permissions -- and against a database 282 ms away that is 1.2-1.4 s of pure
waiting, on every request. One statement does the same work.

But "the same work" is a claim about an AUTHORISATION path, and the failure
mode of getting it wrong is not a slow dashboard: it is a user holding
permissions they should not hold, silently, until someone notices. Unit tests
with a fake cursor cannot settle that, because the question is about the data
in this database -- how many roles there are, whether any role's name collides
with another role's uid, which accounts have a NULL clearance.

So this asks the database. It runs BOTH implementations, for EVERY account in
dll_access_relay, and compares all four returned values. The old implementation
is reproduced below verbatim rather than imported, so the comparison survives
the old code being deleted.

WHAT A DIFFERENCE WOULD MEAN

  permissions differ   STOP. Someone's access changes. Do not deploy.
  role/type/root differ STOP. The identity the guard works from changes.
  no differences       The collapse is safe for this data set, today.

That last caveat is real: this proves it for the rows that exist now, not for
all possible data. The one divergence known from reading the code is called
out explicitly below, and this run is what says whether it bites in practice.

KNOWN DIVERGENCE, BY DESIGN

The old code passed str(user_role) into the role lookup, so an account whose
account_clearance is NULL searched for a role literally named 'None'. The new
query compares against the column, where NULL matches nothing. Both return an
empty permission list unless a role really is named 'None'. This script
reports any account where that matters instead of assuming it does not.

READ-ONLY. Issues only SELECTs, opens and closes its own connections, writes
no file, and prints no secret.

Usage:
    python scripts/verify_permission_parity.py
    python scripts/verify_permission_parity.py --limit 200
    python scripts/verify_permission_parity.py --account <account_uid>
"""

import argparse
import sys

sys.path.insert(0, '.')


# ─────────────────────────────────────────────────────────────────────────────
# The OLD implementation, reproduced verbatim from commit 7767bf5 so that this
# comparison does not depend on the old code still being in the tree.
# ─────────────────────────────────────────────────────────────────────────────

def old_load_user_permissions(cursor, account_uid):
    cursor.execute(
        "SELECT account_clearance, account_type, account_root "
        "FROM dll_access_relay WHERE account_uid = %s AND access_status = 'active'",
        (str(account_uid),)
    )
    if cursor.rowcount == 0:
        return None, None, None, []

    row = cursor.fetchone()
    user_role = row[0]
    account_type = row[1]
    account_root = row[2]

    cursor.execute(
        "SELECT role_uid FROM dll_roles WHERE role_name = %s "
        "AND (is_deleted = FALSE OR is_deleted IS NULL)",
        (str(user_role),)
    )
    if cursor.rowcount == 0:
        cursor.execute(
            "SELECT role_uid FROM dll_roles WHERE role_uid = %s "
            "AND (is_deleted = FALSE OR is_deleted IS NULL)",
            (str(user_role),)
        )
        if cursor.rowcount == 0:
            return user_role, account_type, account_root, []

    role_uid = cursor.fetchone()[0]

    cursor.execute(
        "SELECT p.permission_name FROM dll_role_permissions rp "
        "JOIN dll_permissions p ON rp.permission_uid = p.permission_uid "
        "WHERE rp.role_uid = %s AND (p.is_deleted = FALSE OR p.is_deleted IS NULL)",
        (str(role_uid),)
    )
    return user_role, account_type, account_root, [r[0] for r in cursor.fetchall()]


def new_load_user_permissions(cursor, account_uid, sql):
    cursor.execute(sql, {'uid': str(account_uid)})
    rows = cursor.fetchall()
    if not rows:
        return None, None, None, []
    user_role, account_type, account_root = rows[0][:3]
    return (user_role, account_type, account_root,
            [r[3] for r in rows if r[3] is not None])


# ─────────────────────────────────────────────────────────────────────────────

def comparable(result):
    """Permission ORDER is not part of the contract; membership is."""
    role, acct_type, root, perms = result
    return (role, acct_type, root, sorted(perms), len(perms))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit', type=int, default=0,
                        help='check only this many accounts (0 = all)')
    parser.add_argument('--account', default=None,
                        help='check a single account_uid')
    args = parser.parse_args()

    import psycopg2
    from config import DB_LINK
    from endpoints.globals import _PERMISSIONS_SQL

    print('verify_permission_parity -- read-only')

    conn = psycopg2.connect(DB_LINK)
    conn.autocommit = True          # one bad account must not poison the rest
    try:
        cur = conn.cursor()

        if args.account:
            accounts = [args.account]
        else:
            cur.execute('SELECT account_uid FROM dll_access_relay '
                        'ORDER BY account_uid')
            accounts = [r[0] for r in cur.fetchall()]
            if args.limit:
                accounts = accounts[:args.limit]

        print('accounts to check: %d' % len(accounts))
        print()

        differences = []
        null_clearance = []
        checked = 0

        for account in accounts:
            try:
                old = old_load_user_permissions(cur, account)
                new = new_load_user_permissions(cur, account, _PERMISSIONS_SQL)
            except Exception as error:                     # noqa: BLE001
                differences.append((account, 'EXCEPTION', str(error), ''))
                continue

            checked += 1
            if old[0] is None and old[1] is not None:
                null_clearance.append(account)

            if comparable(old) != comparable(new):
                differences.append((account, 'MISMATCH', old, new))

        cur.close()
    finally:
        conn.close()

    print('checked           %d account(s)' % checked)
    print('NULL clearance    %d (the known divergence applies to these)'
          % len(null_clearance))
    print('differences       %d' % len(differences))
    print()

    if not differences:
        print('  PARITY. Every account returns the same role, account type,')
        print('  account root and permission set from both implementations.')
        print('  The collapse from three round trips to one is safe for this')
        print('  data. Re-run it if the roles or permissions tables change')
        print('  shape -- this proves today\'s rows, not every possible row.')
        return 0

    print('  !! DO NOT DEPLOY. The two implementations disagree.')
    print()
    for account, kind, old, new in differences[:20]:
        print('  %s  %s' % (kind, account))
        if kind == 'MISMATCH':
            o_role, o_type, o_root, o_perms = old
            n_role, n_type, n_root, n_perms = new
            if (o_role, o_type, o_root) != (n_role, n_type, n_root):
                print('      identity  old=%r  new=%r'
                      % ((o_role, o_type, o_root), (n_role, n_type, n_root)))
            if sorted(o_perms) != sorted(n_perms):
                gained = sorted(set(n_perms) - set(o_perms))
                lost = sorted(set(o_perms) - set(n_perms))
                if gained:
                    print('      GAINED    %s' % ', '.join(gained))
                if lost:
                    print('      lost      %s' % ', '.join(lost))
        else:
            print('      %s' % old)
    if len(differences) > 20:
        print('  ... and %d more' % (len(differences) - 20))
    return 1


if __name__ == '__main__':
    sys.exit(main())
