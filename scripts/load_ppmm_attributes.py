#!/usr/bin/env python3
"""
load_ppmm_attributes.py — load PPMM product attributes into the database.

The PPMM matrix is products-as-columns, attributes-as-rows: three descriptor
columns (Level_1_Section, Level_2_Subcategory, Row_Type) followed by one column
per product. This script transposes that into the Phase 2 tables so Waswa can
query it, and so a catalogue change is a re-run rather than a code change.

    Export the PPMM tab to CSV, then:

        python scripts/load_ppmm_attributes.py ppmm_export.csv            # dry run
        python scripts/load_ppmm_attributes.py ppmm_export.csv --commit   # write

Dry run is the default and prints exactly what it would insert. Check that
output before committing: the section-to-table mapping below is a first pass at
a spreadsheet whose row layout was not designed for this, and a wrong mapping
would put marketing phrasing into the capability table, which is precisely what
the authority ladder exists to prevent.

Products are matched by column header against product names and aliases.
Unmatched columns are reported and skipped — never created. A product this
script has not seen approved does not get invented here.
"""

import argparse
import csv
import sys

import psycopg2

sys.path.insert(0, '.')
from config import DB_LINK      # noqa: E402

# Which PPMM section feeds which table. Sections not listed are skipped:
# product costing and 3D DOCS are deliberately out — pricing is Odoo's, and
# document references are Phase 3's job, not a product attribute.
SECTION_MAP = {
    'TELEMATICS FEATURES': ('capability', None),
    'SOFTWARE PLATFORMS':  ('capability', None),
    'HARDWARE COMPATIBILY': ('hardware', None),      # sheet's spelling
    'HARDWARE COMPATIBILITY': ('hardware', None),
    'VALUE ADDED SERVICES': ('capability', None),
    'MARKET SEGMENTS':     ('segment', 'market_segment'),
    'USE CASES':           ('segment', 'use_case'),
}

# Cell values that mean "no".
FALSEY = {'', '-', 'n/a', 'na', 'no', 'false', '0', 'x-', 'none'}

DESCRIPTOR_COLUMNS = 3


def _is_set(value):
    return str(value or '').strip().lower() not in FALSEY


def _clean(value):
    return ' '.join(str(value or '').split()).strip()


def _section_key(section):
    """'2. TELEMATICS FEATURES' -> 'TELEMATICS FEATURES'."""
    text = _clean(section).upper()
    if '.' in text[:4]:
        text = text.split('.', 1)[1].strip()
    return text


def load_products(cur):
    """{lowercased name or alias: product_uid}."""
    cur.execute("SELECT product_name, product_uid FROM abi_products_manager")
    index = {_clean(n).lower(): uid for n, uid in cur.fetchall()}
    cur.execute("SELECT alias, product_uid FROM abi_product_aliases")
    for alias, uid in cur.fetchall():
        index.setdefault(_clean(alias).lower(), uid)
    return index


def parse(csv_path, product_index):
    """Return (rows, unmatched_columns, skipped_sections)."""
    out, unmatched, skipped = [], [], set()

    with open(csv_path, newline='', encoding='utf-8-sig') as handle:
        reader = csv.reader(handle)
        header = None
        for row in reader:
            if any('Level_1_Section' in str(c) for c in row):
                header = [_clean(c) for c in row]
                break
        if not header:
            raise SystemExit(
                "Could not find the header row (no 'Level_1_Section' cell). "
                "Is this the PPMM matrix tab?")

        columns = []
        for position in range(DESCRIPTOR_COLUMNS, len(header)):
            name = header[position]
            if not name:
                continue
            uid = product_index.get(name.lower())
            if uid:
                columns.append((position, name, uid))
            else:
                unmatched.append(name)

        section = ''
        for row in reader:
            if not row or len(row) <= DESCRIPTOR_COLUMNS:
                continue
            if _clean(row[0]):
                section = _clean(row[0])
            key = _section_key(section)
            target = SECTION_MAP.get(key)
            if not target:
                if key:
                    skipped.add(key)
                continue

            kind, segment_kind = target
            label = _clean(row[1]) or _clean(row[2])
            if not label:
                continue

            for position, column_name, uid in columns:
                if position >= len(row):
                    continue
                cell = row[position]
                if not _is_set(cell):
                    continue
                detail = _clean(cell)
                out.append({
                    'product_uid': uid,
                    'product_column': column_name,
                    'kind': kind,
                    'segment_kind': segment_kind,
                    'label': label[:160],
                    'detail': None if detail.lower() in ('true', 'yes', 'y')
                              else detail[:500],
                    'section': key,
                })

    return out, unmatched, sorted(skipped)


def write(cur, rows, source_ref):
    counts = {'capability': 0, 'hardware': 0, 'segment': 0}
    for row in rows:
        if row['kind'] == 'capability':
            cur.execute(
                "INSERT INTO abi_product_capabilities "
                "(product_uid, capability, detail, source_ref, authority_level) "
                "VALUES (%s, %s, %s, %s, 1) "
                "ON CONFLICT (product_uid, capability) DO UPDATE "
                "SET detail = EXCLUDED.detail, source_ref = EXCLUDED.source_ref",
                (row['product_uid'], row['label'], row['detail'], source_ref))
        elif row['kind'] == 'hardware':
            cur.execute(
                "INSERT INTO abi_product_hardware "
                "(product_uid, hardware_name, hardware_role, is_required, "
                " notes, source_ref) VALUES (%s, %s, 'slave', TRUE, %s, %s) "
                "ON CONFLICT (product_uid, hardware_name) DO UPDATE "
                "SET notes = EXCLUDED.notes, source_ref = EXCLUDED.source_ref",
                (row['product_uid'], row['label'], row['detail'], source_ref))
        else:
            cur.execute(
                "INSERT INTO abi_product_segments "
                "(product_uid, segment_kind, segment_value, source_ref) "
                "VALUES (%s, %s, %s, %s) "
                "ON CONFLICT (product_uid, segment_kind, segment_value) "
                "DO UPDATE SET source_ref = EXCLUDED.source_ref",
                (row['product_uid'], row['segment_kind'], row['label'],
                 source_ref))
        counts[row['kind']] += 1

    cur.execute(
        "UPDATE abi_products_manager SET attributes_loaded_at = NOW() "
        "WHERE product_uid IN %s",
        (tuple({r['product_uid'] for r in rows}),))
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('csv_path', help='CSV export of the PPMM matrix tab')
    parser.add_argument('--commit', action='store_true',
                        help='write to the database (default is a dry run)')
    parser.add_argument('--source', default='PPMM matrix export',
                        help='source_ref recorded against every row')
    args = parser.parse_args()

    conn = psycopg2.connect(DB_LINK)
    try:
        with conn:
            with conn.cursor() as cur:
                product_index = load_products(cur)
                if not product_index:
                    raise SystemExit(
                        "No products in abi_products_manager. Run migration 028 "
                        "first.")

                rows, unmatched, skipped = parse(args.csv_path, product_index)

                print(f"Parsed {len(rows)} attribute values.")
                by_kind = {}
                for row in rows:
                    by_kind[row['kind']] = by_kind.get(row['kind'], 0) + 1
                for kind, count in sorted(by_kind.items()):
                    print(f"   {kind:12} {count:6}")

                if unmatched:
                    print(f"\nColumns with no matching product ({len(unmatched)}) "
                          f"— skipped, not created:")
                    for name in unmatched:
                        print(f"   - {name}")
                    print("   Add an alias in abi_product_aliases if one of "
                          "these is an approved product under another name.")

                if skipped:
                    print(f"\nSections skipped (not in SECTION_MAP): "
                          f"{', '.join(skipped)}")

                sample = rows[:15]
                if sample:
                    print("\nSample of what would be written:")
                    for row in sample:
                        detail = f" = {row['detail']}" if row['detail'] else ''
                        print(f"   [{row['kind']:10}] {row['product_column']:16} "
                              f"{row['label']}{detail}")

                if not args.commit:
                    print("\nDry run — nothing written. Re-run with --commit "
                          "once the mapping above looks right.")
                    return

                counts = write(cur, rows, args.source)
                print("\nWritten:")
                for kind, count in sorted(counts.items()):
                    print(f"   {kind:12} {count:6}")
    finally:
        conn.close()


if __name__ == '__main__':
    main()
