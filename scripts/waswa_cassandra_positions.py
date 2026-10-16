#!/usr/bin/env python3
"""
waswa_cassandra_positions.py — the schema of the LIVE position store.

The telemetry hunt found the answer. Postgres dll_location_registry holds
2,027,738 rows and stopped on 06-08-2025. Cassandra holds two tables nobody in
this repository reads:

    dll_location_registry                 (data_latitude, data_longitude)
    dll_location_registry_by_record_ts    (data_latitude, data_longitude)

The second one is the giveaway. "by_record_ts" is a denormalised view keyed for
time-range queries, which is exactly the shape a trip needs and exactly what
waswa_fleet._points was trying to do against the wrong database. And unit
350317173603857 has 194 trips with zero Postgres position rows — its positions
have only ever existed in Cassandra.

So _points must be rewritten against Cassandra. Before writing a line of that,
this prints what is actually there: every column, the primary key (which in
Cassandra decides what you are allowed to ask, not merely how fast it is), and
a few real rows so the date, time and speed formats come from the data rather
than from my assumptions. Getting that wrong silently is how we arrived here.

Read-only.

Usage:
    python scripts/waswa_cassandra_positions.py --imei 350317173603857
    python scripts/waswa_cassandra_positions.py --imei 350317173603857 --rows 8
"""

import argparse
import sys

sys.path.insert(0, '.')
from config import CASSANDRA_KEYSPACE              # noqa: E402

TABLES = ('dll_location_registry', 'dll_location_registry_by_record_ts')


def schema(session, table):
    """Columns and primary key. In Cassandra the key is the contract: a query
    that does not restrict the partition key is a cluster-wide scan, and one
    that restricts the wrong thing is simply refused."""
    rows = list(session.execute(
        "SELECT column_name, kind, position, type FROM system_schema.columns "
        "WHERE keyspace_name = %s AND table_name = %s",
        (CASSANDRA_KEYSPACE, table)))
    if not rows:
        print(f'   !! {table} has no columns in system_schema — does it exist?')
        return None

    part = sorted([r for r in rows if r.kind == 'partition_key'],
                  key=lambda r: r.position)
    clust = sorted([r for r in rows if r.kind == 'clustering'],
                   key=lambda r: r.position)
    other = sorted([r for r in rows if r.kind not in ('partition_key', 'clustering')],
                   key=lambda r: r.column_name)

    print(f'\n   PARTITION KEY : '
          f'{", ".join(f"{r.column_name} ({r.type})" for r in part) or "(none?)"}')
    if clust:
        print(f'   CLUSTERING    : '
              f'{", ".join(f"{r.column_name} ({r.type})" for r in clust)}')
    print(f'   other columns : {len(other)}')
    for r in other:
        print(f'       {r.column_name:<34} {r.type}')
    return [r.column_name for r in part], [r.column_name for r in clust], \
           [r.column_name for r in rows]


def sample(session, table, part_cols, all_cols, imei, limit):
    """A few real rows. The formats in them are the specification."""
    imei_col = next((c for c in part_cols if 'imei' in c.lower()), None)
    if imei_col and imei:
        cql = f'SELECT * FROM {table} WHERE {imei_col} = %s LIMIT {int(limit)}'
        args = (str(imei),)
        print(f'\n   sample: WHERE {imei_col} = {imei}')
    else:
        # No IMEI in the partition key, so we cannot ask for one unit without a
        # scan. Take whatever the ring hands back — enough to read the formats.
        cql = f'SELECT * FROM {table} LIMIT {int(limit)}'
        args = ()
        if imei:
            print(f'\n   sample: the partition key is '
                  f'{part_cols} — not the IMEI, so this is an unfiltered peek')
        else:
            print('\n   sample: unfiltered peek')

    try:
        rows = list(session.execute(cql, args))
    except Exception as exc:                        # noqa: BLE001
        print(f'   !! {str(exc).splitlines()[0][:140]}')
        return

    if not rows:
        print('   (no rows came back)')
        return

    interesting = [c for c in all_cols if any(
        k in c.lower() for k in ('imei', 'lat', 'lon', 'speed', 'date', 'time',
                                 'stamp', 'geocod', 'location', 'idx', 'ts'))]
    for n, row in enumerate(rows, 1):
        print(f'\n   -- row {n} ' + '-' * 58)
        for c in interesting:
            v = getattr(row, c, None)
            if v is None or v == '':
                continue
            text = str(v)
            print(f'      {c:<32} {text[:88]}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--imei', help='a unit known to be live, e.g. 350317173603857')
    ap.add_argument('--rows', type=int, default=4, help='sample rows per table')
    args = ap.parse_args()

    try:
        from endpoints.devices import get_cassandra_session
        session = get_cassandra_session()
    except Exception as exc:                        # noqa: BLE001
        print(f'!! could not connect to Cassandra: {str(exc)[:140]}')
        return 1
    if session is None:
        print('!! no Cassandra session')
        return 1

    for table in TABLES:
        print('\n' + '=' * 76)
        print(f'== {CASSANDRA_KEYSPACE}.{table}')
        print('=' * 76)
        got = schema(session, table)
        if not got:
            continue
        part, _clust, all_cols = got
        sample(session, table, part, all_cols, args.imei, args.rows)

    print('\n' + '=' * 76)
    print('What this decides, before any code is written:')
    print('  * which table _points queries, and what it may filter on;')
    print('  * the real date and time formats, so _stamp is told rather than')
    print('    guessing a third time;')
    print('  * whether a speed column exists — without one, "and it was fast"')
    print('    cannot be answered from positions at all;')
    print('  * whether geocoded_location is filled in, which would let route')
    print('    questions be answered from text already stored, with no billed')
    print('    Places call per point.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
