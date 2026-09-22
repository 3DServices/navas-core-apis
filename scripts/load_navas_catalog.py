#!/usr/bin/env python3
"""
load_navas_catalog.py — load NAVAS_CATALOG_*.xlsx into abi_catalog_objects.

    pip install openpyxl
    python scripts/load_navas_catalog.py NAVAS_CATALOG_v26.03.30.xlsx
    python scripts/load_navas_catalog.py NAVAS_CATALOG_v26.03.30.xlsx --commit
    python scripts/load_navas_catalog.py --reconcile          # report only, no file

## What this does and does not do

The catalogue is a selection document: eight sections of approved objects, each
with a short description and ten columns arguing why it made the cut. It has no
product codes, no prices, and no mapping from a feature to a service type.

So it cannot repair the products missing 3D-PRD codes, and it cannot fill in a
missing service_type. Those facts are not in the file, and a loader that
invented them would be worse than no loader. What it can do is define which
objects are approved, which turns one useless answer into three useful ones:
a product that does not exist, a product that exists on paper but has no
record, and a record nobody approved.

## Read the reconciliation before you commit

--commit writes abi_catalog_objects and nothing else. It never touches
abi_products_manager: this script does not edit the product master, it gives
you the report that says what is wrong with it. Fixing those rows is a business
decision about real products, not a migration.
"""

import argparse
import os
import re
import sys
import unicodedata

import psycopg2

sys.path.insert(0, '.')
from config import DB_LINK      # noqa: E402

try:
    import openpyxl
except ImportError:
    openpyxl = None

# The section header names in the sheet, mapped to the object_kind stored.
KINDS = {
    'SERVICE TYPES': 'service_type',
    'CORE FEATURES': 'core_feature',
    'APPS - APP LIB': 'app',
    'APPs - APP LIB': 'app',
    'MARKET PLACE': 'marketplace',
    'TECH VAS': 'tech_vas',
    'CMS INTERFACE': 'cms_interface',
    'MASTER DEVICES': 'master_device',
    'SLAVE DEVICES': 'slave_device',
}

NAME_COL, DESC_COL, FIRST_RATIONALE_COL, LAST_RATIONALE_COL = 2, 3, 4, 13

# Looked up when no path is given, so the usual command fits on one line.
CATALOG_DIR = os.path.join('database', 'catalog')
DEFAULT_GLOB = 'NAVAS_CATALOG*'


def find_default():
    if not os.path.isdir(CATALOG_DIR):
        return None
    import fnmatch
    names = sorted(n for n in os.listdir(CATALOG_DIR)
                   if fnmatch.fnmatch(n, DEFAULT_GLOB)
                   and n.lower().endswith(('.xlsx', '.xlsm')))
    return os.path.join(CATALOG_DIR, names[-1]) if names else None


def clean(value):
    if value is None:
        return ''
    out = unicodedata.normalize('NFKC', str(value)).replace(' ', ' ')
    out = out.replace('\r', ' ').replace('\n', ' / ')
    return re.sub(r'\s+', ' ', out).strip()


def slug(name):
    """The join key. Must match navas_slug() in migration 038.

    '+' is kept: iVMS and iVMS+ are different products at different prices,
    and collapsing them is a worse error than matching neither.
    """
    return re.sub(r'[^a-z0-9+]+', '', (name or '').lower())


def split_device(kind, name):
    """Pull family / connectivity / rank / vendor-model out of a device name.

    Master: 'Standard Vehicle_2G Only_1_Teltonika FMB920'
    Slave:  'BLE Fuel Level Sensor_S1_TD-BLE_Escort_BLE_...'

    Returned as NULLs rather than guesses when the name does not split the way
    the convention says — a device wrongly filed under a connectivity it does
    not have is exactly the sort of thing compatibility_check must not repeat.
    """
    if kind not in ('master_device', 'slave_device'):
        return None, None, None, None
    parts = [p.strip() for p in name.split('_') if p.strip()]
    if len(parts) < 3:
        return None, None, None, None
    if kind == 'master_device':
        family, connectivity, rank = parts[0], parts[1], parts[2]
        vendor_model = parts[3] if len(parts) > 3 else None
        if not re.fullmatch(r'\d+', rank):
            rank, vendor_model = None, parts[2]
        return family, connectivity, rank, vendor_model
    family, rank = parts[0], parts[1]
    vendor_model = ' '.join(parts[2:4]) if len(parts) > 2 else None
    if not re.fullmatch(r'S\d+', rank, re.I):
        rank, vendor_model = None, ' '.join(parts[1:3])
    return family, None, rank, vendor_model


def parse(path):
    if openpyxl is None:
        raise SystemExit("openpyxl is required:  pip install openpyxl")
    workbook = openpyxl.load_workbook(path, data_only=True)
    worksheet = workbook.worksheets[0]
    version = clean(worksheet.title) or os.path.basename(path)

    def cell(row, col):
        return clean(worksheet.cell(row=row, column=col).value)

    objects, kind, ordinal, unknown_sections = [], None, 0, []
    for row in range(1, (worksheet.max_row or 0) + 1):
        name = cell(row, NAME_COL)
        if not name:
            continue
        if cell(row, DESC_COL).lower() == 'description':
            key = name.upper()
            kind = KINDS.get(key) or KINDS.get(name)
            if kind is None:
                unknown_sections.append(name)
            ordinal = 0
            continue
        if kind is None:
            continue

        ordinal += 1
        rationale = ' | '.join(
            v for v in (cell(row, c)
                        for c in range(FIRST_RATIONALE_COL, LAST_RATIONALE_COL + 1))
            if v)
        description = cell(row, DESC_COL)
        short = description.split(' / ')[0].strip() if description else None
        family, connectivity, rank, vendor_model = split_device(kind, name)
        objects.append({
            'catalog_version': version, 'object_kind': kind,
            'object_name': name, 'object_slug': slug(name),
            'short_name': (short or None), 'description': description or None,
            'rationale': rationale or None, 'device_family': family,
            'connectivity': connectivity, 'device_rank': rank,
            'vendor_model': vendor_model, 'ordinal': ordinal,
            'source_ref': f'{os.path.basename(path)} :: {version}',
        })
    return version, objects, unknown_sections


def write(cur, objects):
    written = 0
    for obj in objects:
        cur.execute(
            "INSERT INTO abi_catalog_objects "
            "(catalog_version, object_kind, object_name, object_slug, "
            " short_name, description, rationale, device_family, connectivity, "
            " device_rank, vendor_model, ordinal, source_ref) "
            "VALUES (%(catalog_version)s,%(object_kind)s,%(object_name)s,"
            " %(object_slug)s,%(short_name)s,%(description)s,%(rationale)s,"
            " %(device_family)s,%(connectivity)s,%(device_rank)s,"
            " %(vendor_model)s,%(ordinal)s,%(source_ref)s) "
            "ON CONFLICT (catalog_version, object_kind, object_slug) "
            "DO UPDATE SET description = EXCLUDED.description, "
            "              rationale   = EXCLUDED.rationale, "
            "              short_name  = EXCLUDED.short_name, "
            "              loaded_at   = NOW()",
            obj)
        written += cur.rowcount
    return written


def reconcile(cur):
    cur.execute(
        "SELECT status, COUNT(*) FROM vw_navas_catalog_reconciliation "
        "GROUP BY status ORDER BY COUNT(*) DESC")
    rows = cur.fetchall() if cur.rowcount > 0 else []
    if not rows:
        print("Nothing to reconcile — is abi_catalog_objects loaded?")
        return

    print(f"\n{'count':>6}  status")
    for status, count in rows:
        print(f"{count:>6}  {status}")

    for status, heading, limit in (
            ('no matching catalogue object (platform, or named differently)',
             'Product rows matching no catalogue object. NOT necessarily '
             'unapproved: the catalogue lists what is inside the platforms, '
             'not OLIWA or UKO themselves', 20),
            ('catalogue object has no product record',
             'Approved catalogue objects with no product row', 15),
            ('matched, but product has no code',
             'Matched, but the product row has no code', 15),
            ('matched, but product has no service type',
             'Matched, but the product row has no service type', 15)):
        cur.execute(
            "SELECT COALESCE(object_name, product_name), object_kind, "
            "       product_uid, matching_products "
            "FROM vw_navas_catalog_reconciliation WHERE status = %s "
            "ORDER BY 1 LIMIT %s", (status, limit))
        items = cur.fetchall() if cur.rowcount > 0 else []
        if not items:
            continue
        print(f"\n--- {heading} ---")
        for name, kind, uid, matches in items:
            flag = (f'  <- {matches} products share this name; '
                    f'the one shown was picked by a tiebreak'
                    if (matches or 0) > 1 else '')
            print(f"   {(name or '')[:52]:52} {(kind or ''):<14} "
                  f"{(uid or '')[:24]}{flag}")

    cur.execute("SELECT service_type, products, drift, approved_spelling "
                "FROM vw_navas_service_type_drift")
    drift = cur.fetchall() if cur.rowcount > 0 else []
    if drift:
        print("\n--- service_type values that do not match the approved five ---")
        for value, count, kind, approved in drift:
            suffix = f'  -> should be {approved!r}' if approved else ''
            print(f"   {value[:34]:34} {count:>3} product(s)  {kind}{suffix}")
        print("   The approved vocabulary: "
              "AI & Video, Fuel Telematics, Vehicle Telematics, "
              "Goods & IoT, Personnel Tracing.")

    print("\nNothing above is fixed by this script. It writes "
          "abi_catalog_objects only and never edits abi_products_manager — "
          "which product a code or service type belongs to is a business "
          "decision, not something a loader may infer.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', nargs='?',
                        help='the catalogue workbook; defaults to the newest '
                             'database/catalog/NAVAS_CATALOG*.xlsx')
    parser.add_argument('--commit', action='store_true',
                        help='write (default is a dry run)')
    parser.add_argument('--reconcile', action='store_true',
                        help='report against what is already loaded, read no file')
    args = parser.parse_args()

    if not args.source and not args.reconcile:
        args.source = find_default()
        if not args.source:
            parser.error(
                f'no workbook given and none found in {CATALOG_DIR}. Pass the '
                f'path, or use --reconcile to report on what is loaded.')
        print(f"Using {args.source}")

    conn = psycopg2.connect(DB_LINK)
    try:
        with conn:
            with conn.cursor() as cur:
                if args.source:
                    version, objects, unknown = parse(args.source)
                    print(f"Catalogue version: {version}")
                    if unknown:
                        print(f"   UNKNOWN SECTION(S), not loaded: "
                              f"{', '.join(unknown)}")
                        print("   Add them to KINDS in this script before "
                              "loading, or their objects are silently dropped.")

                    kinds = {}
                    for obj in objects:
                        kinds[obj['object_kind']] = kinds.get(obj['object_kind'], 0) + 1
                    print(f"\n{'count':>6}  object kind")
                    for kind, count in sorted(kinds.items()):
                        print(f"{count:>6}  {kind}")
                    print(f"{len(objects):>6}  TOTAL")

                    dupes = {}
                    for obj in objects:
                        key = (obj['object_kind'], obj['object_slug'])
                        dupes[key] = dupes.get(key, 0) + 1
                    repeated = [k for k, n in dupes.items() if n > 1]
                    if repeated:
                        print(f"\n   {len(repeated)} name(s) repeated within "
                              f"their section; the later row wins:")
                        for kind, key in repeated[:10]:
                            print(f"      {kind}: {key}")

                    if args.commit:
                        written = write(cur, objects)
                        print(f"\n{written} row(s) written to abi_catalog_objects.")
                    else:
                        print("\nDry run — nothing written. Add --commit.")

                if args.commit or args.reconcile:
                    reconcile(cur)
                elif args.source:
                    print("Run again with --commit to load, then the "
                          "reconciliation report follows automatically.")
    finally:
        conn.close()


if __name__ == '__main__':
    main()
