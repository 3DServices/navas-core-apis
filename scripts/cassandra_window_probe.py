#!/usr/bin/env python3
"""
cassandra_window_probe.py — why does Cassandra return nothing for a window
Postgres has 1,934 rows for?

B1 failed: for unit 867556044727322 over 15-07-2025 to 01-08-2025, the legacy
Postgres query returned 1,934 fixes and location_store returned 0. Exactly one
of three things is true, and they have completely different consequences:

  A. The two stores do not overlap in time. The device listener wrote to
     Postgres until 06-08-2025 and to Cassandra from some later date. If so,
     there is NO window where both hold data, B1 as designed cannot ever pass,
     and the parity method itself has to change — not the reader.

  B. local_system_datestamp in Cassandra is not DD-MM-YYYY. It is part of the
     partition key and it is text, so per-day equality on the wrong format
     matches nothing and raises no error. If so, the reader has a real bug.

  C. This unit's rows live under a different partition value — a different
     imei spelling, or in dll_location_registry but not the _by_record_ts
     copy. If so, the reader is querying the wrong table for this unit.

This distinguishes them. It does not guess: every answer below is read from
the cluster.

Read-only. Nothing is written anywhere.

Usage:
    python scripts/cassandra_window_probe.py --imei 867556044727322 \
        --from 15-07-2025 --to 01-08-2025
"""

import argparse
import sys
from datetime import date, datetime, timedelta

sys.path.insert(0, '.')
from config import CASSANDRA_KEYSPACE, DB_LINK          # noqa: E402

TABLES = ('dll_location_registry_by_record_ts', 'dll_location_registry')


def key_of(session, table):
    """The partition and clustering key, which decides what may be asked."""
    rows = list(session.execute(
        "SELECT column_name, kind, position, type FROM system_schema.columns "
        "WHERE keyspace_name = %s AND table_name = %s",
        (CASSANDRA_KEYSPACE, table)))
    if not rows:
        return None, None, {}
    part = [r for r in sorted(rows, key=lambda r: r.position)
            if r.kind == 'partition_key']
    clust = [r for r in sorted(rows, key=lambda r: r.position)
             if r.kind == 'clustering']
    types = {r.column_name: r.type for r in rows}
    return part, clust, types


def days(from_date, to_date):
    f = datetime.strptime(from_date, '%d-%m-%Y').date()
    t = datetime.strptime(to_date, '%d-%m-%Y').date()
    out, d = [], f
    while d <= t:
        out.append(d)
        d += timedelta(days=1)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--imei', required=True)
    ap.add_argument('--from', dest='from_date', default='15-07-2025')
    ap.add_argument('--to', dest='to_date', default='01-08-2025')
    args = ap.parse_args()

    from flask import Flask
    app = Flask(__name__)
    app.config['db_link'] = DB_LINK
    with app.app_context():
        from endpoints.devices import get_cassandra_session
        session = get_cassandra_session()
        if session is None:
            print('!! no Cassandra session')
            return 1
        return probe(session, args)


def probe(session, args):
    imei = ''.join(str(args.imei).split())

    print('=' * 72)
    print('1. WHAT THE KEYS ALLOW')
    print('=' * 72)
    for table in TABLES:
        part, clust, types = key_of(session, table)
        if part is None:
            print(f'\n   {table}: NOT PRESENT in {CASSANDRA_KEYSPACE}')
            continue
        print(f'\n   {table}')
        print(f'      partition key : '
              f'{", ".join(f"{r.column_name} ({r.type})" for r in part)}')
        print(f'      clustering    : '
              f'{", ".join(f"{r.column_name} ({r.type})" for r in clust) or "(none)"}')
        dt = types.get('local_system_datestamp')
        print(f'      datestamp type: {dt}')
        if dt and dt != 'text':
            print(f'      !! location_store passes a STRING for this column.')

    print('\n' + '=' * 72)
    print('2. PER-DAY COUNTS IN THE B1 WINDOW  (cause B: format / cause A: time)')
    print('=' * 72)
    print(f'   unit {imei}, {args.from_date} to {args.to_date}')
    stmt = session.prepare(
        "SELECT data_device_imei FROM dll_location_registry_by_record_ts "
        "WHERE data_device_imei = ? AND local_system_datestamp = ?")
    total = 0
    for d in days(args.from_date, args.to_date):
        label = d.strftime('%d-%m-%Y')
        try:
            n = len(list(session.execute(stmt, (imei, label))))
        except Exception as error:                      # noqa: BLE001
            print(f'      {label} : ERROR {str(error)[:60]}')
            continue
        total += n
        if n:
            print(f'      {label} : {n} row(s)')
    print(f'   total in window : {total}')
    if total == 0:
        print('   -> the window is genuinely empty for this partition spelling.')

    print('\n' + '=' * 72)
    print('3. WHERE IS THIS UNIT\'S DATA IN TIME?  (cause A)')
    print('=' * 72)
    print('   probing the 1st and 15th of each month, May 2025 to today:')
    found_days = []
    d = date(2025, 5, 1)
    today = date.today()
    while d <= today:
        for day in (1, 15):
            try:
                probe_day = d.replace(day=day)
            except ValueError:
                continue
            if probe_day > today:
                continue
            label = probe_day.strftime('%d-%m-%Y')
            try:
                n = len(list(session.execute(stmt, (imei, label))))
            except Exception:                           # noqa: BLE001
                n = -1
            if n > 0:
                found_days.append((label, n))
        d = (d.replace(day=28) + timedelta(days=4)).replace(day=1)
    if found_days:
        print(f'   rows found on {len(found_days)} probe day(s):')
        for label, n in found_days:
            print(f'      {label} : {n} row(s)')
        print(f'\n   earliest probe day with data : {found_days[0][0]}')
        print(f'   latest probe day with data   : {found_days[-1][0]}')
    else:
        print('   NO rows on any probe day from May 2025 to today.')
        print('   -> this unit has no rows in this table under this imei.')

    print('\n' + '=' * 72)
    print('4. RAW ROWS, SO THE FORMATS COME FROM THE DATA  (cause B)')
    print('=' * 72)
    sample_day = found_days[-1][0] if found_days else None
    if sample_day:
        full = session.prepare(
            "SELECT data_device_imei, local_system_datestamp, "
            "local_system_timestamp, record_timestamp, data_longitude, "
            "data_latitude, data_idx FROM dll_location_registry_by_record_ts "
            "WHERE data_device_imei = ? AND local_system_datestamp = ?")
        for r in list(session.execute(full, (imei, sample_day)))[:3]:
            print(f'\n      imei            : {r.data_device_imei!r} '
                  f'({type(r.data_device_imei).__name__})')
            print(f'      datestamp       : {r.local_system_datestamp!r} '
                  f'({type(r.local_system_datestamp).__name__})')
            print(f'      timestamp       : {r.local_system_timestamp!r}')
            print(f'      record_timestamp: {r.record_timestamp!r}')
            print(f'      lon, lat        : {r.data_longitude!r}, '
                  f'{r.data_latitude!r}')
            print(f'      data_idx        : {r.data_idx!r}')
    else:
        print('   skipped — no day with rows to sample.')

    print('\n' + '=' * 72)
    print('5. IS THE IMEI SPELLED DIFFERENTLY?  (cause C)')
    print('=' * 72)
    print('   one unrestricted peek, LIMIT 5, to see real partition values:')
    try:
        for r in list(session.execute(
                "SELECT data_device_imei, local_system_datestamp "
                "FROM dll_location_registry_by_record_ts LIMIT 5")):
            print(f'      imei={r.data_device_imei!r}  '
                  f'datestamp={r.local_system_datestamp!r}')
    except Exception as error:                          # noqa: BLE001
        print(f'      refused: {str(error)[:70]}')

    print('\n' + '=' * 72)
    print('VERDICT')
    print('=' * 72)
    if total > 0:
        print('   Rows DO exist in the B1 window. location_store is at fault —')
        print('   compare section 4 formats against _DATE_FORMATS.')
    elif found_days:
        print(f'   The unit has data, but not in the B1 window (earliest probe')
        print(f'   day with rows: {found_days[0][0]}). Cause A: the stores do')
        print('   not overlap. B1 needs a window both stores hold, or a')
        print('   different proof method.')
    else:
        print('   No rows for this imei on any probe day. Cause C: wrong')
        print('   partition value or wrong table. Compare section 5.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
