#!/usr/bin/env python3
"""
location_store_parity.py — prove the new reader before any route uses it.

location_store reads positions from Cassandra. data.py reads them from Postgres.
Swapping four routes onto a new reader on the strength of "it looks right" is how
trip history quietly starts lying, so this compares the two against each other
over a window where the Postgres copy still HAS data — July–August 2025, before
it stopped taking rows.

If they agree there, the new reader reproduces the old behaviour and the
difference after August 2025 is the Postgres copy being stale, which is the
whole point. If they disagree there, the new reader is wrong and nothing should
be switched.

Three things are compared, because a count alone would hide an ordering bug:

  * how many fixes each returns after dedupe
  * the first and last coordinate, which catches a reversed or shuffled order
  * the set of coordinates, which catches a different dedupe rule

Read-only.

Usage:
    python scripts/location_store_parity.py --imei 867556044727322 \
        --from 15-07-2025 --to 01-08-2025
    python scripts/location_store_parity.py --imei 867556044727322 \
        --from 15-07-2025 --to 01-08-2025 --limit 500
"""

import argparse
import sys

import psycopg2

sys.path.insert(0, '.')
from config import DB_LINK                                  # noqa: E402
from endpoints import location_store                        # noqa: E402

LEGACY = """
SELECT data_longitude, data_latitude, speed_log, data_hdop,
       local_system_datestamp, record_io_events_uid, geocoded_location,
       local_system_timestamp, data_connected_satelites, batch_uid, data_idx,
       ROW_NUMBER() OVER (ORDER BY data_idx DESC) AS row_index
  FROM (SELECT *, ROW_NUMBER() OVER (PARTITION BY data_longitude, data_latitude
                                     ORDER BY data_idx DESC) AS row_num
          FROM dll_location_registry
         WHERE data_device_imei = %s
           AND TO_DATE(local_system_datestamp, 'DD-MM-YYYY')
               BETWEEN TO_DATE(%s, 'DD-MM-YYYY') AND TO_DATE(%s, 'DD-MM-YYYY')
       ) AS subquery
 WHERE row_num = 1
 ORDER BY data_idx DESC
 LIMIT %s OFFSET %s
"""


def coord(row):
    """A comparable coordinate. The two stores keep different float precision
    in places, so compare at six decimals — about 10 cm, far finer than GPS."""
    return (round(float(row[0]), 6), round(float(row[1]), 6))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--imei', required=True)
    ap.add_argument('--from', dest='from_date', required=True,
                    help='DD-MM-YYYY, in a window where Postgres still has rows')
    ap.add_argument('--to', dest='to_date', required=True)
    ap.add_argument('--limit', type=int, default=2000)
    ap.add_argument('--offset', type=int, default=0)
    args = ap.parse_args()

    print(f'unit   : {args.imei}')
    print(f'window : {args.from_date} to {args.to_date}')
    print(f'page   : limit {args.limit}, offset {args.offset}')

    conn = psycopg2.connect(DB_LINK)
    try:
        with conn.cursor() as cur:
            cur.execute(LEGACY, (str(args.imei), args.from_date, args.to_date,
                                 args.limit, args.offset))
            legacy = cur.fetchall() if cur.rowcount > 0 else []
    finally:
        conn.close()

    from flask import Flask
    app = Flask(__name__)
    app.config['db_link'] = DB_LINK
    with app.app_context():
        from endpoints.devices import get_cassandra_session
        try:
            session = get_cassandra_session()
        except Exception as error:                      # noqa: BLE001
            print(f'\n!! Cassandra unreachable: {str(error)[:120]}')
            return 1
        try:
            rows, truncated = location_store.fixes(
                session, args.imei, args.from_date, args.to_date,
                limit=args.limit, offset=args.offset)
        except location_store.PositionsUnavailable as error:
            print(f'\n!! position store unavailable: {error}')
            return 1
    fresh = [location_store.as_history_tuple(r) for r in rows]

    print(f'\n   Postgres (legacy query) : {len(legacy)} fix(es)')
    print(f'   Cassandra (new reader)  : {len(fresh)} fix(es)'
          + ('  [span truncated]' if truncated else ''))

    if not legacy and not fresh:
        print('\n   Both empty. Pick a window where the Postgres copy has rows —')
        print('   its newest is 06-08-2025. Nothing is proven by two blanks.')
        return 1
    if not legacy:
        print('\n   Postgres has nothing here, so there is nothing to compare')
        print('   against. Choose an earlier window to validate the reader.')
        return 1

    problems = []

    if len(legacy) != len(fresh):
        problems.append(f'count differs: {len(legacy)} vs {len(fresh)}')

    if legacy and fresh:
        if coord(legacy[0]) != coord(fresh[0]):
            problems.append(f'first fix differs: {coord(legacy[0])} '
                            f'vs {coord(fresh[0])} — ordering is not the same')
        if coord(legacy[-1]) != coord(fresh[-1]):
            problems.append(f'last fix differs: {coord(legacy[-1])} '
                            f'vs {coord(fresh[-1])}')

    left, right = {coord(r) for r in legacy}, {coord(r) for r in fresh}
    only_pg, only_cass = left - right, right - left
    if only_pg:
        problems.append(f'{len(only_pg)} coordinate(s) only in Postgres, '
                        f'e.g. {sorted(only_pg)[:2]}')
    if only_cass:
        problems.append(f'{len(only_cass)} coordinate(s) only in Cassandra, '
                        f'e.g. {sorted(only_cass)[:2]}')

    print()
    if not problems:
        print('   MATCH — same count, same order, same coordinates.')
        print('   The new reader reproduces the old query on data both stores')
        print('   hold, so a difference after 06-08-2025 is the Postgres copy')
        print('   being stale. Safe to switch the routes.')
        return 0

    print('   !! DIFFERS:')
    for p in problems:
        print(f'      - {p}')
    print('\n   Do not switch any route yet. Note that a coordinate present in')
    print('   one store and not the other may be real — the two were written by')
    print('   different pipelines — so check a few by hand before assuming the')
    print('   reader is at fault.')
    return 1


if __name__ == '__main__':
    sys.exit(main())
