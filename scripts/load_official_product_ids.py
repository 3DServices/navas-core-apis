#!/usr/bin/env python3
"""
load_official_product_ids.py — load the product register, and repair from it.

    python scripts/load_official_product_ids.py database/catalog/Official_Product_IDs_v26.csv
    python scripts/load_official_product_ids.py <file> --commit      # load register
    python scripts/load_official_product_ids.py --repair             # dry run
    python scripts/load_official_product_ids.py --repair --commit    # write fills

Accepts the .csv or the .xlsx; columns Product_ID, Product_Name,
Product_Description, Service Type.

## The two halves

Loading the register writes abi_official_products and nothing else. Repairing
writes product_code and service_type onto abi_products_manager rows — the only
place in this whole build where a script edits the product master — so it is a
separate, explicit step with its own --commit.

## What repair will and will not touch

It fills a field only when that field is EMPTY and the register has a value.
It never overwrites a value that disagrees with the register: a live code that
differs is a fact about the business that somebody entered on purpose, and the
report names it instead.

It also refuses the case that looks identical from one row away. Where a
product name exists twice — once as the surviving coded row, once as a UUID row
created when the catalogue was rebuilt — writing the register's code onto the
second row puts one 3D-PRD code on two rows. That is a merge, not a fill, and
which row survives depends on what points at it: tokens, subscriptions,
installed assets. This script stops and lists them.
"""

import argparse
import csv
import os
import re
import sys

import psycopg2

sys.path.insert(0, '.')
from config import DB_LINK      # noqa: E402

COLUMNS = ('Product_ID', 'Product_Name', 'Product_Description', 'Service Type')

# Where the register lives in the repo. Looked up when no path is given, so the
# usual command is short enough to paste into a terminal without wrapping — a
# wrapped path becomes its own command line and the script just prints usage.
CATALOG_DIR = os.path.join('database', 'catalog')
DEFAULT_GLOB = 'Official_Product_IDs*'


def find_default():
    if not os.path.isdir(CATALOG_DIR):
        return None
    import fnmatch
    names = sorted(n for n in os.listdir(CATALOG_DIR)
                   if fnmatch.fnmatch(n, DEFAULT_GLOB)
                   and n.lower().endswith(('.csv', '.xlsx', '.xlsm')))
    return os.path.join(CATALOG_DIR, names[-1]) if names else None


def slug(value):
    """Must match navas_slug() in migration 038, including keeping '+'."""
    return re.sub(r'[^a-z0-9+]+', '', (value or '').lower())


def read_rows(path):
    if path.lower().endswith(('.xlsx', '.xlsm')):
        try:
            import openpyxl
        except ImportError:
            raise SystemExit("openpyxl is required for .xlsx: pip install openpyxl")
        worksheet = openpyxl.load_workbook(path, data_only=True).worksheets[0]
        rows = list(worksheet.iter_rows(values_only=True))
        header = [str(h or '').strip() for h in rows[0]]
        return [dict(zip(header, ['' if v is None else str(v).strip() for v in r]))
                for r in rows[1:] if any(r)]
    with open(path, encoding='utf-8-sig', newline='') as handle:
        return [{k: (v or '').strip() for k, v in row.items()}
                for row in csv.DictReader(handle)]


def load_register(cur, path, commit):
    rows = read_rows(path)
    if not rows:
        raise SystemExit(f"{path} has no rows.")
    missing = [c for c in COLUMNS if c not in rows[0]]
    if missing:
        raise SystemExit(f"{path} is missing column(s): {', '.join(missing)}. "
                         f"Found: {', '.join(rows[0])}")

    version = re.sub(r'[^A-Za-z0-9._-]+', '_',
                     os.path.splitext(os.path.basename(path))[0])[:40]

    seen, duplicates = {}, []
    for row in rows:
        key = slug(row['Product_Name'])
        if key in seen:
            duplicates.append((row['Product_ID'], seen[key], row['Product_Name']))
        seen[key] = row['Product_ID']

    print(f"Register: {len(rows)} product(s), {len(seen)} distinct name(s)")
    if duplicates:
        print("   Names appearing twice in the register — only the last is "
              "stored, so check these:")
        for new, old, name in duplicates:
            print(f"      {name!r}: {old} and {new}")

    types = {}
    for row in rows:
        types[row['Service Type']] = types.get(row['Service Type'], 0) + 1
    print(f"\n{'count':>6}  service type (as the register spells it)")
    for value, count in sorted(types.items(), key=lambda kv: -kv[1]):
        print(f"{count:>6}  {value}")

    if not commit:
        print("\nDry run — register not written. Add --commit.")
        return version, False

    for row in rows:
        cur.execute(
            "INSERT INTO abi_official_products "
            "(product_id, product_name, product_slug, description, "
            " service_type, register_version, source_ref) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s) "
            "ON CONFLICT (product_id) DO UPDATE SET "
            "  product_name = EXCLUDED.product_name, "
            "  product_slug = EXCLUDED.product_slug, "
            "  description  = EXCLUDED.description, "
            "  service_type = EXCLUDED.service_type, "
            "  loaded_at    = NOW()",
            (row['Product_ID'], row['Product_Name'], slug(row['Product_Name']),
             row['Product_Description'] or None, row['Service Type'] or None,
             version, os.path.basename(path)))
    print(f"\n{len(rows)} register row(s) written.")
    return version, True


def repair(cur, commit, fill_description):
    cur.execute("SELECT verdict, COUNT(*) FROM vw_navas_product_repair "
                "GROUP BY verdict ORDER BY COUNT(*) DESC")
    verdicts = cur.fetchall() if cur.rowcount > 0 else []
    if not verdicts:
        print("Nothing to repair — is abi_official_products loaded?")
        return

    print(f"\n{'count':>6}  verdict")
    for verdict, count in verdicts:
        print(f"{count:>6}  {verdict}")

    for verdict, heading in (
            ('MERGE: another row already holds this code',
             'DUPLICATE PRODUCTS — a human must decide which row survives. '
             'Nothing is written for these'),
            ('CONFLICT: live code differs from the register',
             'Live product_code disagrees with the register. Not overwritten'),
            ('CONFLICT: live service type differs from the register',
             'Live service_type disagrees with the register. Not overwritten'),
            ('not in the official register',
             'Product rows with no register entry (ad-hoc, or named '
             'differently — an alias would fix the latter)')):
        cur.execute(
            "SELECT product_name, product_uid, product_code, service_type, "
            "       official_code, official_service_type "
            "FROM vw_navas_product_repair WHERE verdict = %s "
            "ORDER BY product_name", (verdict,))
        rows = cur.fetchall() if cur.rowcount > 0 else []
        if not rows:
            continue
        print(f"\n--- {heading} ({len(rows)}) ---")
        for name, uid, code, stype, ocode, ostype in rows:
            detail = ''
            if verdict.startswith('MERGE'):
                detail = f'  register says {ocode}, already on another row'
            elif 'code differs' in verdict:
                detail = f'  live={code!r} register={ocode!r}'
            elif 'service type differs' in verdict:
                detail = f'  live={stype!r} register={ostype!r}'
            print(f"   {name[:26]:26} {uid[:38]:38}{detail}")

    cur.execute("SELECT product_id, product_name, service_type "
                "FROM vw_navas_register_unbuilt")
    unbuilt = cur.fetchall() if cur.rowcount > 0 else []
    if unbuilt:
        print(f"\n--- In the register, but no product row exists ({len(unbuilt)}) ---")
        for code, name, stype in unbuilt:
            print(f"   {code:<12} {name[:28]:28} {stype or ''}")

    cur.execute(
        "SELECT product_uid, product_name, official_code, "
        "       official_service_type, official_description, verdict "
        "FROM vw_navas_product_repair WHERE verdict LIKE 'fill:%' "
        "ORDER BY official_code")
    fills = cur.fetchall() if cur.rowcount > 0 else []
    print(f"\n--- Safe to fill ({len(fills)}) ---")
    for uid, name, code, stype, _desc, verdict in fills:
        what = 'code + service type' if 'code' in verdict else 'service type'
        print(f"   {name[:26]:26} -> {code:<12} {stype[:24]:24} ({what})")

    if not fills:
        return
    if not commit:
        print("\nDry run — nothing written to abi_products_manager. "
              "Add --commit.")
        return

    written = 0
    for uid, _name, code, stype, description, verdict in fills:
        sets = ["service_type = COALESCE(NULLIF(service_type, ''), %s)"]
        params = [stype]
        if 'code' in verdict:
            sets.insert(0, "product_code = COALESCE(NULLIF(product_code, ''), %s)")
            params.insert(0, code)
        if fill_description:
            sets.append("product_description = "
                        "COALESCE(NULLIF(product_description, ''), %s)")
            params.append(description)
        params.append(uid)
        cur.execute(
            f"UPDATE abi_products_manager SET {', '.join(sets)} "
            f"WHERE product_uid = %s", params)
        written += cur.rowcount
    print(f"\n{written} product row(s) updated.")
    print("Re-run with --repair to confirm the verdicts moved to 'ok'.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', nargs='?',
                        help='the register file; defaults to the newest '
                             'database/catalog/Official_Product_IDs*')
    parser.add_argument('--commit', action='store_true',
                        help='write (default is a dry run)')
    parser.add_argument('--repair', action='store_true',
                        help='report, and with --commit fill, product rows')
    parser.add_argument('--fill-description', action='store_true',
                        help='also fill an empty product_description')
    args = parser.parse_args()

    if not args.source and not args.repair:
        args.source = find_default()
        if not args.source:
            parser.error(
                f'no register file given and none found in {CATALOG_DIR}. '
                f'Pass the path, or use --repair to work from what is already '
                f'loaded.')
        print(f"Using {args.source}")

    conn = psycopg2.connect(DB_LINK)
    try:
        with conn:
            with conn.cursor() as cur:
                loaded = True
                if args.source:
                    _version, loaded = load_register(cur, args.source, args.commit)
                if args.repair:
                    if not loaded:
                        print("\nLoad the register first (--commit), then "
                              "--repair.")
                        return
                    repair(cur, args.commit, args.fill_description)
                elif args.source and args.commit:
                    print("\nNext:  python scripts/load_official_product_ids.py "
                          "--repair")
    finally:
        conn.close()


if __name__ == '__main__':
    main()
