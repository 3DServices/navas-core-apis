#!/usr/bin/env python3
"""Seed the Oliwa, Oliwa+ and VEBA token packages into dll_tokens_registry.

Source: database/seeds/tokens_oliwa_veba_v26.11.11.json, extracted from
Navas_IoT_Unit_Cost_v26.06.12.xlsx (sheet NVS.TKN.v26.11.11 for Oliwa and
Oliwa+, sheet Token_SKUs_v26.06.23 for VEBA). 20 SKUs per product, each
loaded once per currency (UGX and KES) -> 120 rows.

Run from the repo root, after run_migration_059.py:

    python scripts/seed_tokens_oliwa_veba.py            # dry run, writes nothing
    python scripts/seed_tokens_oliwa_veba.py --apply    # writes, one transaction

Idempotent: a row is matched on (token_sku, currency). Existing rows are
left alone unless --update-existing is passed, which refreshes their price,
name, description and billing fields (token_id is never changed, so wallets
and subscriptions that point at a token keep working).

Missing products ('oliwa', 'oliwa plus', 'veba') are created in
abi_products_manager with the service_type the mobile taxonomy expects.
"""

import argparse
import json
import sys
import uuid
from datetime import datetime

import psycopg2
import pytz

sys.path.insert(0, '.')
from config import DB_LINK  # noqa: E402

SEED_FILE = 'database/seeds/tokens_oliwa_veba_v26.11.11.json'
CURRENCIES = ('UGX', 'KES')
TIMEZONE = pytz.timezone('Africa/Nairobi')

# Product name (lowercase, as stored) -> service_type used if we must create it.
PRODUCTS = {
    'oliwa': 'Vehicles',
    'oliwa plus': 'Vehicles',
    'veba': 'Add-on-App',
}

# SKU suffix -> (token_type, billing_unit, billing_trigger, billing_conditions).
# Same 20 suffixes in every product family. Types/units/triggers are the ones
# tokens_billing.py accepts.
_BILLING = {
    'T01':   ('time', 'hour', 'continuous', []),
    'T12':   ('time', 'hour', 'continuous', []),
    'T24':   ('time', 'period', 'continuous', []),
    'T07':   ('time', 'period', 'continuous', []),
    'T30':   ('time', 'period', 'continuous', []),
    'T90':   ('time', 'period', 'continuous', []),
    'T365':  ('time', 'period', 'continuous', []),
    'B30':   ('time', 'period', 'continuous', []),
    'B90':   ('time', 'period', 'continuous', ['premium_sla']),
    'E100':  ('event', 'event', 'on_event', []),
    'E500':  ('event', 'event', 'on_event', []),
    'A50':   ('event', 'inference', 'on_event', []),
    'A200':  ('event', 'inference', 'on_event', []),
    'ACT1':  ('action', 'command', 'on_command', []),
    'ACT10': ('action', 'command', 'on_command', []),
    'RPT':   ('compliance', 'report', 'on_schedule', []),
    'RPT10': ('compliance', 'report', 'on_schedule', []),
    'WKD':   ('conditional', 'period', 'on_threshold', ['weekend_fri_1800_to_mon_0600']),
    'NGT':   ('conditional', 'period', 'on_threshold', ['night_1800_to_0600']),
    'ROAM':  ('conditional', 'period', 'on_threshold', ['out_of_country']),
}


def token_name(product, short_name, currency):
    """Same 'PRODUCT_' prefix tokens_billing._compose_token_name gives, plus
    the currency so the UGX and KES rows of one SKU have distinct names."""
    return f"{product.upper()}_{short_name} ({currency})"


def ensure_products(cur, apply):
    uids = {}
    for name, service_type in PRODUCTS.items():
        cur.execute(
            "SELECT product_uid FROM abi_products_manager WHERE product_name = %s",
            (name,),
        )
        row = cur.fetchone()
        if row:
            uids[name] = row[0]
            print(f"   product  ok      {name!r} -> {row[0]}")
            continue
        uid = str(uuid.uuid4())
        uids[name] = uid
        print(f"   product  CREATE  {name!r} (service_type={service_type!r}) -> {uid}")
        if apply:
            cur.execute(
                "INSERT INTO abi_products_manager (product_uid, product_name, service_type) "
                "VALUES (%s, %s, %s)",
                (uid, name, service_type),
            )
    return uids


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--apply', action='store_true',
                    help='write to the database (default is a dry run)')
    ap.add_argument('--update-existing', action='store_true',
                    help='refresh price/name/description of rows already seeded')
    args = ap.parse_args()

    with open(SEED_FILE, encoding='utf-8') as fh:
        tokens = json.load(fh)['tokens']

    unknown = sorted({t['suffix'] for t in tokens} - set(_BILLING))
    if unknown:
        sys.exit(f"No billing mapping for SKU suffixes: {unknown}")

    print(f"{'APPLY' if args.apply else 'DRY RUN'}: {len(tokens)} SKUs x "
          f"{len(CURRENCIES)} currencies from {SEED_FILE}\n")

    conn = psycopg2.connect(DB_LINK)
    created = updated = skipped = 0
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'dll_tokens_registry' AND column_name = 'token_sku'"
        )
        if cur.fetchone() is None:
            sys.exit("dll_tokens_registry.token_sku is missing - run run_migration_059.py first.")

        product_uids = ensure_products(cur, args.apply)
        print()
        now = datetime.now(TIMEZONE).strftime("%d-%m-%Y %I:%M:%S%p")

        for t in tokens:
            ttype, unit, trigger, conditions = _BILLING[t['suffix']]
            for cur_code in CURRENCIES:
                amount = t['price_ugx'] if cur_code == 'UGX' else t['price_kes']
                name = token_name(t['product'], t['name'], cur_code)
                values = (name, ttype, product_uids[t['product']],
                          json.dumps(t['parameters']), unit, trigger,
                          json.dumps(conditions), 'asset', str(amount), cur_code,
                          t['description'])

                cur.execute(
                    "SELECT token_id FROM dll_tokens_registry "
                    "WHERE token_sku = %s AND UPPER(token_currency) = %s",
                    (t['sku'], cur_code),
                )
                row = cur.fetchone()
                if row and not args.update_existing:
                    skipped += 1
                    print(f"   skip    {t['sku']:<24} {cur_code} {amount:>10}  (exists)")
                    continue
                if row:
                    updated += 1
                    print(f"   update  {t['sku']:<24} {cur_code} {amount:>10}  {name}")
                    if args.apply:
                        cur.execute(
                            "UPDATE dll_tokens_registry SET token_name=%s, token_type=%s, "
                            "token_product_uid=%s, token_parameters=%s, billing_unit=%s, "
                            "billing_trigger=%s, billing_conditions=%s, billing_scope=%s, "
                            "token_amount=%s, token_currency=%s, token_description=%s "
                            "WHERE token_id=%s",
                            values + (row[0],),
                        )
                    continue
                created += 1
                print(f"   create  {t['sku']:<24} {cur_code} {amount:>10}  {name}")
                if args.apply:
                    cur.execute(
                        "INSERT INTO dll_tokens_registry "
                        "(token_name, token_type, token_product_uid, token_parameters, "
                        " billing_unit, billing_trigger, billing_conditions, billing_scope, "
                        " token_amount, token_currency, token_description, "
                        " token_id, token_sku, date_created) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                        values + (str(uuid.uuid4()), t['sku'], now),
                    )

        if args.apply:
            conn.commit()
        else:
            conn.rollback()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    print(f"\n{created} to create, {updated} to update, {skipped} already present."
          + ("" if args.apply else "  Nothing written - re-run with --apply."))


if __name__ == '__main__':
    main()
