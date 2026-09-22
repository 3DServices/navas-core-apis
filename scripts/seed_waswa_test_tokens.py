#!/usr/bin/env python3
"""
seed_waswa_test_tokens.py — a token account Waswa can actually report on.

Why this exists: nothing in navas-core-apis produces a populated token account.
The two finance.py insert paths write 0 or nothing, the columns have no
defaults, and only the external billing daemon turns
'units_unfined_waiting_for_first_use' into a number. So no amount of clicking
through the app in a dev environment yields an account with a real balance,
and Waswa cannot be shown to state a correct figure until one exists.

This seeds four token packs against an EXISTING client, in the four states that
matter:

    awaiting first use   the sentinel, exactly as production stores it
    partly consumed      a real remaining figure
    exhausted            zero remaining, which must read as a real zero
    expired              status expired

The last two are the important pair: Waswa must tell "0 units left" apart from
"units unreadable", and only real data proves it does.

Shape fidelity: the deprecated token_hours_* columns are filled with the same
deprecation notices production holds, so anything reading them meets the same
string it meets live. Seeding clean numbers there would hide the very bug the
read-path fixes address.

Safety:
  * Dry run by default; --commit to write.
  * Creates no accounts, users or credentials. It attaches packs to a client
    that already exists, so you log in as you already do.
  * Every seeded row is tagged WASWA-SEED- in its token_billing_uid, and
    --remove deletes exactly those rows and nothing else.
  * Columns are introspected, so it sets only columns this database has.

    python scripts/seed_waswa_test_tokens.py --client-uid <uid>
    python scripts/seed_waswa_test_tokens.py --client-uid <uid> --commit
    python scripts/seed_waswa_test_tokens.py --client-uid <uid> --remove --commit
"""

import argparse
import sys
import uuid

import psycopg2

sys.path.insert(0, '.')
from config import DB_LINK      # noqa: E402

SEED_TAG = 'WASWA-SEED-'
AWAITING = 'units_unfined_waiting_for_first_use'
HOURS_LEFT_NOTICE = 'column deprecated use token_units_left column'
HOURS_USED_NOTICE = 'column deprecated use token_used_units column'

# (label, token_status, token_units_left, token_used_units)
PACKS = [
    ('awaiting first use', 'new',     AWAITING, AWAITING),
    ('partly consumed',    'active',  '120',    '80'),
    ('exhausted',          'active',  '0',      '200'),
    ('expired',            'expired', '0',      '500'),
]


def columns_of(cur, table):
    cur.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = %s", (table,))
    return {r[0] for r in cur.fetchall()}


def pick_product(cur, requested=None):
    """A product to seed the token against.

    Prefers the official PPMM catalogue (product_uid like 3D-PRD-nnn, seeded by
    migration 028) over anything else in the table. A database that also holds
    ad-hoc products created through /billing/products/create will otherwise
    surface one of those alphabetically, and a token pointing at "api book"
    makes active_products resolve to something meaningless.
    """
    if requested:
        cur.execute(
            "SELECT product_uid, product_name, product_code "
            "FROM abi_products_manager WHERE product_uid = %s", (requested,))
        if not cur.rowcount:
            raise SystemExit(f"No product with product_uid {requested}.")
        return cur.fetchone()

    cur.execute(
        "SELECT product_uid, product_name, product_code "
        "FROM abi_products_manager "
        "ORDER BY CASE WHEN LOWER(product_name) = 'ivms' THEN 0 "
        "              WHEN product_uid LIKE '3D-PRD-%%'    THEN 1 "
        "              ELSE 2 END, "
        "         product_name LIMIT 1")
    return cur.fetchone() if cur.rowcount else None


def ensure_registry_token(cur, product_uid, columns, commit):
    """A registry token pointing at a product that exists.

    The orphaned-product problem is the reason this is seeded rather than
    reused: most registry tokens point at product rows that are gone.
    """
    cur.execute(
        "SELECT token_id FROM dll_tokens_registry WHERE token_name = %s",
        ('WASWA SEED TOKEN',))
    if cur.rowcount:
        return cur.fetchone()[0], False

    token_id = str(uuid.uuid4())
    values = {
        'token_id': token_id,
        'token_name': 'WASWA SEED TOKEN',
        'token_type': 'time',
        'token_product_uid': product_uid,
        'token_currency': 'UGX',
        'token_amount': '0',
        'billing_unit': 'hour',
        'billing_trigger': 'continuous',
        'billing_scope': 'asset',
    }
    usable = {k: v for k, v in values.items() if k in columns}
    if commit:
        cur.execute(
            f"INSERT INTO dll_tokens_registry ({', '.join(usable)}) "
            f"VALUES ({', '.join(['%s'] * len(usable))})",
            list(usable.values()))
    return token_id, True


def seed(cur, client_uid, token_id, columns, commit):
    written = []
    for index, (label, status, units_left, used_units) in enumerate(PACKS, 1):
        billing_uid = f'{SEED_TAG}{index}-{client_uid[:12]}'
        cur.execute(
            "SELECT 1 FROM dll_user_token_accounts WHERE token_billing_uid = %s",
            (billing_uid,))
        if cur.rowcount:
            written.append((label, billing_uid, 'already present'))
            continue

        values = {
            'client_uid': client_uid,
            'token_balance': token_id,          # holds the token_id, not a balance
            'token_status': status,
            'token_billing_uid': billing_uid,
            'token_units_left': units_left,
            'token_used_units': used_units,
            'token_hours_left': HOURS_LEFT_NOTICE,
            'token_hours_used': HOURS_USED_NOTICE,
        }
        usable = {k: v for k, v in values.items() if k in columns}
        if commit:
            cur.execute(
                f"INSERT INTO dll_user_token_accounts ({', '.join(usable)}) "
                f"VALUES ({', '.join(['%s'] * len(usable))})",
                list(usable.values()))
        written.append((label, billing_uid,
                        'seeded' if commit else 'to seed'))
    return written


def remove(cur, client_uid, commit):
    cur.execute(
        "SELECT token_billing_uid FROM dll_user_token_accounts "
        "WHERE token_billing_uid LIKE %s AND client_uid = %s",
        (SEED_TAG + '%', client_uid))
    rows = [r[0] for r in cur.fetchall()] if cur.rowcount > 0 else []
    if commit and rows:
        cur.execute(
            "DELETE FROM dll_user_token_accounts "
            "WHERE token_billing_uid LIKE %s AND client_uid = %s",
            (SEED_TAG + '%', client_uid))
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--client-uid', required=True,
                        help='an existing client_uid to attach the packs to')
    parser.add_argument('--commit', action='store_true',
                        help='write (default is a dry run)')
    parser.add_argument('--remove', action='store_true',
                        help='delete this client\'s seeded packs instead')
    parser.add_argument('--product-uid',
                        help='seed against this product instead of the '
                             'auto-picked one (use a 3D-PRD- code)')
    args = parser.parse_args()

    conn = psycopg2.connect(DB_LINK)
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT client_name FROM dll_client_accounts "
                    "WHERE client_uid = %s", (args.client_uid,))
                if not cur.rowcount:
                    raise SystemExit(
                        f"No client with client_uid {args.client_uid}. This "
                        f"script attaches packs to an existing client; it does "
                        f"not create accounts.")
                client_name = cur.fetchone()[0]
                print(f"Client: {client_name} ({args.client_uid})")

                if args.remove:
                    rows = remove(cur, args.client_uid, args.commit)
                    print(f"\n{len(rows)} seeded pack(s) "
                          f"{'deleted' if args.commit else 'would be deleted'}:")
                    for billing_uid in rows:
                        print(f"   - {billing_uid}")
                    if not args.commit:
                        print("\nDry run — nothing deleted. Add --commit.")
                    return

                product = pick_product(cur, args.product_uid)
                if not product:
                    raise SystemExit(
                        "abi_products_manager is empty — run migration 028 first.")
                product_uid, product_name, product_code = product
                print(f"Product: {product_name} ({product_uid})")
                if not (product_code or '').startswith('3D-PRD-'):
                    print("   WARNING: not a product from the official PPMM "
                          "catalogue. Migration 028 seeds that catalogue —")
                    print("   run it first, or pass --product-uid to choose "
                          "one deliberately.")

                registry_cols = columns_of(cur, 'dll_tokens_registry')
                account_cols = columns_of(cur, 'dll_user_token_accounts')

                token_id, created = ensure_registry_token(
                    cur, product_uid, registry_cols, args.commit)
                print(f"Registry token: {token_id} "
                      f"({'new' if created else 'reused'})")

                written = seed(cur, args.client_uid, token_id,
                               account_cols, args.commit)
                print(f"\n{'Seeded' if args.commit else 'Would seed'} packs:")
                for label, billing_uid, outcome in written:
                    print(f"   {label:20} {billing_uid:34} {outcome}")

                if not args.commit:
                    print("\nDry run — nothing written. Add --commit.")
                    return

                print("\nExpect from /assistant/context after this:")
                print("   token_units_left    120  (from the partly-consumed pack)")
                print("   token_units_used    780")
                print("   packs_awaiting_first_use  1 of the seeded 4")
                print("   active_products     the product above, now resolvable")
                print("\nThe exhausted pack is the one that matters: Waswa must")
                print("report its 0 as a real zero, not as an unreadable value.")
    finally:
        conn.close()


if __name__ == '__main__':
    main()
