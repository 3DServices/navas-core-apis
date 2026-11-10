#!/usr/bin/env python3
"""
dedupe_impact.py — what does the coordinate dedupe actually throw away?

The self-check passed nine properties on 15-08-2025 and reported something it
was not designed to judge: 899 raw rows became 3 fixes. The reader is faithful
— the legacy SQL deduped the same way — but faithful to a rule nobody has seen
run against live data, because the table it ran on stopped taking rows in
August 2025.

The rule is:

    PARTITION BY data_longitude, data_latitude ORDER BY data_idx DESC
    ... WHERE row_num = 1

One row per distinct coordinate, across the WHOLE window, keeping the newest.
So a vehicle that parks at the same depot every night has all of those nights
collapsed into a single fix dated the last one. The earlier days are not
reported as empty — they are simply absent, and the route returns success.

This measures the loss rather than arguing about it. For each day, and then
for the whole window, it counts:

    raw          every row Cassandra holds
    per-day      distinct coordinates within that one day
    window-wide  distinct coordinates across the whole window  <- what ships

The gap between the last two columns is history that global dedupe destroys.
If it is zero, the rule is harmless here and B2 ships as written. If it is
large, the dedupe needs a day component before any route is switched, and that
is a bug in the legacy SQL that moving stores would have carried forward.

It also reports how many fixes a MOVING day produces, because a parked day
collapsing to 3 points is correct behaviour and must not be mistaken for the
bug.

Read-only.

Usage:
    python scripts/dedupe_impact.py --imei 867556044727322 --from 12-08-2025 --to 20-08-2025
    python scripts/dedupe_impact.py --imei 862846042652860 --from 12-08-2025 --to 20-08-2025
"""

import argparse
import sys
from datetime import datetime, timedelta

sys.path.insert(0, '.')
from config import DB_LINK                              # noqa: E402

RAW = ("SELECT data_longitude, data_latitude, record_timestamp, "
       "local_system_timestamp "
       "FROM dll_location_registry_by_record_ts "
       "WHERE data_device_imei = ? AND local_system_datestamp = ?")


def days(from_date, to_date):
    f = datetime.strptime(from_date, '%d-%m-%Y').date()
    t = datetime.strptime(to_date, '%d-%m-%Y').date()
    out, d = [], f
    while d <= t:
        out.append(d.strftime('%d-%m-%Y'))
        d += timedelta(days=1)
    return out


def num(value):
    try:
        return float(str(value).replace(',', '').strip())
    except (TypeError, ValueError):
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--imei', required=True)
    ap.add_argument('--from', dest='from_date', default='12-08-2025')
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
        stmt = session.prepare(RAW)

        per_day = []
        all_coords = set()
        total_raw = 0
        for day in window:
            try:
                rows = list(session.execute(stmt, (imei, day)))
            except Exception as error:                  # noqa: BLE001
                print(f'   {day}: ERROR {str(error)[:50]}')
                continue
            coords = set()
            for r in rows:
                lon, lat = num(r.data_longitude), num(r.data_latitude)
                if lon is None or lat is None or (lon == 0 and lat == 0):
                    continue
                coords.add((lon, lat))
            total_raw += len(rows)
            all_coords |= coords
            per_day.append((day, len(rows), len(coords)))

    print(f'unit {imei}, {args.from_date} to {args.to_date}\n')
    print(f'   {"day":<12} {"raw rows":>9} {"distinct coords that day":>26}')
    print('   ' + '-' * 50)
    for day, raw, coords in per_day:
        if raw:
            print(f'   {day:<12} {raw:>9} {coords:>26}')
    sum_per_day = sum(c for _, _, c in per_day)

    print('\n' + '=' * 62)
    print('WHAT THE DEDUPE COSTS')
    print('=' * 62)
    print(f'   raw rows across the window        : {total_raw}')
    print(f'   distinct coords summed per day    : {sum_per_day}')
    print(f'   distinct coords window-wide       : {len(all_coords)}'
          '   <- what the route returns')
    lost = sum_per_day - len(all_coords)
    print(f'\n   fixes lost to window-wide dedupe  : {lost}')

    print('\n' + '=' * 62)
    if total_raw == 0:
        print('   No rows in this window. Pick days the overlap finder showed:')
        print('   12-08 to 20-08 had rows every day for 867556044727322.')
        return 1
    if lost == 0:
        print('   The rule costs nothing here: no coordinate repeats across')
        print('   days, so window-wide dedupe equals per-day dedupe. B2 ships')
        print('   as written.')
    else:
        pct = 100.0 * lost / sum_per_day if sum_per_day else 0
        print(f'   Window-wide dedupe drops {lost} fix(es), {pct:.0f}% of the')
        print('   per-day total. Those are real positions on real days that')
        print('   the route will not return, without reporting anything wrong.')
        print('\n   This is legacy behaviour, not a new bug — but it was')
        print('   invisible while the source table was dead. Two options:')
        print('\n     a) ship B2 as-is (pure source change, one variable at a')
        print('        time), then fix the dedupe as its own ticket')
        print('     b) add a day component to the dedupe key first, so')
        print('        trips/history stops losing days the moment it works')
    moving = [(d, r, c) for d, r, c in per_day if c > 10]
    parked = [(d, r, c) for d, r, c in per_day if 0 < c <= 3]
    print(f'\n   days that look like driving (>10 coords) : {len(moving)}')
    print(f'   days that look parked (<=3 coords)       : {len(parked)}')
    if parked and not moving:
        print('\n   Every day here looks parked, so this unit cannot tell us')
        print('   what a moving day returns. Re-run against a unit that moved.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
