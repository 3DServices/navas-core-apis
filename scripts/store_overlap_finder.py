#!/usr/bin/env python3
"""
store_overlap_finder.py — is there ANY day both position stores hold?

B1 compared Postgres and Cassandra over 15-07-2025 to 01-08-2025 and found
1,934 against 0. The window probe then showed why: Cassandra has nothing on
01-08-2025 and 899 rows on 15-08-2025, while the Postgres copy's newest row is
dated 06-08-2025. The listener moved between those dates, so the only possible
overlap is the handful of days in between — which nobody has counted.

This counts every day from 25-07-2025 to 20-08-2025 in three places:

    Postgres   dll_location_registry                 (the legacy copy)
    Cassandra  dll_location_registry_by_record_ts    (what location_store reads)
    Cassandra  dll_location_registry                 (keyed by imei alone)

A day where Postgres and either Cassandra table are both non-zero is a day B1
can run on. If no such day exists the two stores are disjoint, B1 as designed
can never pass, and the reader must be proved another way — which is what
location_store_selfcheck.py does.

The third column matters on its own. That table partitions on
data_device_imei alone, so it may cover dates the _by_record_ts copy does not.
If it holds July, parity is possible after all.

Read-only.

Usage:
    python scripts/store_overlap_finder.py --imei 867556044727322
    python scripts/store_overlap_finder.py --imei 867556044727322 \
        --from 25-07-2025 --to 20-08-2025
"""

import argparse
import sys
from datetime import datetime, timedelta

import psycopg2

sys.path.insert(0, '.')
from config import DB_LINK                              # noqa: E402

PG_COUNT = """
SELECT COUNT(*) FROM dll_location_registry
 WHERE data_device_imei = %s AND local_system_datestamp = %s
"""


def days(from_date, to_date):
    f = datetime.strptime(from_date, '%d-%m-%Y').date()
    t = datetime.strptime(to_date, '%d-%m-%Y').date()
    out, d = [], f
    while d <= t:
        out.append(d.strftime('%d-%m-%Y'))
        d += timedelta(days=1)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--imei', required=True)
    ap.add_argument('--from', dest='from_date', default='25-07-2025')
    ap.add_argument('--to', dest='to_date', default='20-08-2025')
    args = ap.parse_args()

    imei = ''.join(str(args.imei).split())
    window = days(args.from_date, args.to_date)

    from flask import Flask
    app = Flask(__name__)
    app.config['db_link'] = DB_LINK
    with app.app_context():
        from endpoints.devices import get_cassandra_session
        session = get_cassandra_session()
        if session is None:
            print('!! no Cassandra session')
            return 1

        by_ts = session.prepare(
            "SELECT data_device_imei FROM dll_location_registry_by_record_ts "
            "WHERE data_device_imei = ? AND local_system_datestamp = ?")
        plain = session.prepare(
            "SELECT data_device_imei FROM dll_location_registry "
            "WHERE data_device_imei = ? AND local_system_datestamp = ?")

        conn = psycopg2.connect(DB_LINK)
        rows = []
        try:
            with conn.cursor() as cur:
                for day in window:
                    cur.execute(PG_COUNT, (imei, day))
                    pg = cur.fetchone()[0]
                    try:
                        a = len(list(session.execute(by_ts, (imei, day))))
                    except Exception as error:          # noqa: BLE001
                        a = f'ERR {str(error)[:18]}'
                    try:
                        b = len(list(session.execute(plain, (imei, day))))
                    except Exception as error:          # noqa: BLE001
                        b = f'ERR {str(error)[:18]}'
                    rows.append((day, pg, a, b))
        finally:
            conn.close()

    print(f'unit {imei}, {args.from_date} to {args.to_date}\n')
    print(f'   {"day":<12} {"Postgres":>10} {"C* by_record_ts":>17} '
          f'{"C* registry":>13}   both?')
    print('   ' + '-' * 62)
    overlap = []
    for day, pg, a, b in rows:
        na = a if isinstance(a, int) else 0
        nb = b if isinstance(b, int) else 0
        both = pg > 0 and (na > 0 or nb > 0)
        if both:
            overlap.append((day, pg, na, nb))
        mark = ' <== OVERLAP' if both else ''
        print(f'   {day:<12} {pg:>10} {a:>17} {b:>13}{mark}')

    pg_days = [d for d, pg, _, _ in rows if pg > 0]
    ts_days = [d for d, _, a, _ in rows if isinstance(a, int) and a > 0]
    pl_days = [d for d, _, _, b in rows if isinstance(b, int) and b > 0]

    print('\n   Postgres has rows on         : '
          f'{len(pg_days)} day(s)' + (f'  ({pg_days[0]} .. {pg_days[-1]})'
                                      if pg_days else ''))
    print('   C* by_record_ts has rows on  : '
          f'{len(ts_days)} day(s)' + (f'  ({ts_days[0]} .. {ts_days[-1]})'
                                      if ts_days else ''))
    print('   C* dll_location_registry on  : '
          f'{len(pl_days)} day(s)' + (f'  ({pl_days[0]} .. {pl_days[-1]})'
                                      if pl_days else ''))

    print('\n' + '=' * 66)
    if overlap:
        day, pg, na, nb = overlap[0]
        print(f'   OVERLAP EXISTS on {len(overlap)} day(s).')
        print(f'   Run B1 on one of them — a single day is a valid window:')
        print(f'\n     python scripts/location_store_parity.py --imei {imei} \\')
        print(f'         --from {day} --to {day}')
        print(f'\n   ({day}: Postgres {pg}, by_record_ts {na}, registry {nb})')
        print('\n   One day of agreement is thinner evidence than three weeks,')
        print('   so run location_store_selfcheck.py as well, not instead.')
    else:
        print('   NO OVERLAP. The two stores are disjoint in time, so no')
        print('   window exists where they can be compared. This is not a')
        print('   reader bug and B1 as written can never pass.')
        print('\n   Prove the reader against the store it actually reads:')
        print(f'\n     python scripts/location_store_selfcheck.py --imei {imei} \\')
        print('         --day 15-08-2025')
    return 0


if __name__ == '__main__':
    sys.exit(main())
