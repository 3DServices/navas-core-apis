#!/usr/bin/env python3
"""
find_moving_unit.py — find a unit that actually drives, before designing B4.

Both units measured so far are idle. 867556044727322 did not move at all in
nine days: whole-window extent 37 metres, speed 0 on all 8,007 fixes, and its
390 "distinct positions" are GPS drift inside a 30-metre circle.
862846042652860 managed 3.5-6.3 km on four of nine days, and its position
field latches between updates, so 99.3% of its successive fixes are 0 m apart
despite real kilometres travelled.

Neither observation covers the case trip history exists for: a vehicle driving
a route. That is also the case a 25 m radius could damage, by merging a slow
crawl through traffic into one fake stop. Designing the stop detector on two
stationary vehicles would be designing it blind.

So this ranks candidates by what the platform itself recorded, then checks
that record against the position store:

  1. dll_trips_auditor, ended trips in the window, per unit: how many trips
     and how far the ODOMETER says they went. The odometer is the vehicle's
     own measurement and what the Trips report quotes.

  2. for the strongest candidates, the Cassandra fixes on their busiest trip
     day: extent, path length, distinct coordinates, speed range.

Step 2 is also a cross-check worth having on its own. If the trips table
claims 40 km on a day whose fixes span 30 metres, one of the two is wrong, and
we would rather find that out now than encode it into a dwell calculation.

Read-only.

Usage:
    python scripts/find_moving_unit.py
    python scripts/find_moving_unit.py --days 90 --top 6
"""

import argparse
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from math import atan2, cos, radians, sin, sqrt

import psycopg2

sys.path.insert(0, '.')
from config import DB_LINK                              # noqa: E402

TRIPS = """
SELECT device_imei, trip_date, start_mileage, end_mileage, trip_status
  FROM dll_trips_auditor
 WHERE trip_date BETWEEN %s AND %s
   AND lower(trim(trip_status)) = 'ended'
"""

FIXES = ("SELECT data_longitude, data_latitude, record_timestamp, speed_log "
         "FROM dll_location_registry_by_record_ts "
         "WHERE data_device_imei = ? AND local_system_datestamp = ?")


def num(value):
    """A number, or None. dll_trips_auditor writes placeholder text such as
    'NoData' where a NULL belongs, so this must not raise on them."""
    try:
        text = str(value).replace(',', '').strip()
    except (TypeError, ValueError):
        return None
    if not text or text.lower() in ('nodata', 'no-data', 'none', 'null',
                                    'incoming', 'n/a', '-'):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def metres(a, b):
    lon1, lat1 = radians(a[0]), radians(a[1])
    lon2, lat2 = radians(b[0]), radians(b[1])
    h = (sin((lat2 - lat1) / 2) ** 2
         + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2)
    return 6371000.0 * 2 * atan2(sqrt(h), sqrt(1 - h))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--days', type=int, default=120,
                    help='how far back to look for ended trips')
    ap.add_argument('--top', type=int, default=5,
                    help='how many candidates to probe in Cassandra')
    args = ap.parse_args()

    end = date.today()
    start = end - timedelta(days=args.days)
    print(f'ended trips between {start} and {end}\n')

    conn = psycopg2.connect(DB_LINK)
    try:
        with conn.cursor() as cur:
            cur.execute(TRIPS, (start, end))
            rows = cur.fetchall() if cur.rowcount > 0 else []
            # The route calls check_device() before it reads a position, and
            # that reads device_billing_status from POSTGRES
            # dll_device_basic_data. A unit can have trips and Cassandra fixes
            # and still be absent here, in which case trips/history answers
            # 'Routing Failed, Device Cant be found' and tests nothing.
            cur.execute("SELECT device_imei, device_billing_status "
                        "FROM dll_device_basic_data")
            billing = {str(i).strip(): str(s or '').strip()
                       for i, s in (cur.fetchall() if cur.rowcount > 0 else [])}
    finally:
        conn.close()

    if not rows:
        print('!! no ended trips in that window. Widen it with --days.')
        return 1

    trips = defaultdict(int)
    km = defaultdict(float)
    measured = defaultdict(int)
    busiest = defaultdict(lambda: defaultdict(int))
    for imei, trip_date, m0, m1, _status in rows:
        key = str(imei or '').strip()
        if not key:
            continue
        trips[key] += 1
        busiest[key][trip_date] += 1
        a, b = num(m0), num(m1)
        if a is not None and b is not None and b >= a:
            km[key] += (b - a)
            measured[key] += 1

    print(f'{len(rows)} ended trip(s) across {len(trips)} unit(s)\n')
    print('=' * 74)
    print('1. WHAT THE TRIPS TABLE RECORDS')
    print('=' * 74)
    print(f'   {"unit":<18} {"trips":>6} {"odo km":>9} {"busiest day":>13} '
          f'{"billing":>12}')
    print('   ' + '-' * 66)
    # A unit the route will reject is not a candidate, however far it drove.
    ranked = sorted(trips, key=lambda k: (
        billing.get(k, '').lower() == 'running', km[k], trips[k]),
        reverse=True)
    for key in ranked[:15]:
        day = max(busiest[key], key=lambda d: busiest[key][d])
        state = billing.get(key) or 'NOT REGISTERED'
        print(f'   {key:<18} {trips[key]:>6} {km[key]:>9.1f} '
              f'{str(day):>13} {state:>12}')
    if len(ranked) > 15:
        print(f'   ... and {len(ranked) - 15} more')

    print('\n' + '=' * 74)
    print('2. DOES THE POSITION STORE AGREE?')
    print('=' * 74)
    from flask import Flask
    app = Flask(__name__)
    app.config['db_link'] = DB_LINK
    with app.app_context():
        from endpoints.devices import get_cassandra_session
        session = get_cassandra_session()
        if session is None:
            print('   !! no Cassandra session; section 1 still stands.')
            return 1
        stmt = session.prepare(FIXES)

        verdicts = []
        for key in ranked[:args.top]:
            day = max(busiest[key], key=lambda d: busiest[key][d])
            label = day.strftime('%d-%m-%Y') if hasattr(day, 'strftime') \
                else str(day)
            try:
                found = list(session.execute(stmt, (key, label)))
            except Exception as error:                  # noqa: BLE001
                print(f'\n   {key}  {label}: ERROR {str(error)[:40]}')
                continue
            pts = []
            for r in found:
                lon, lat = num(r.data_longitude), num(r.data_latitude)
                if lon is None or lat is None or (lon == 0 and lat == 0):
                    continue
                if r.record_timestamp is None:
                    continue
                pts.append(((lon, lat), r.record_timestamp, num(r.speed_log)))
            print(f'\n   unit {key}, busiest trip day {label}')
            print(f'      trips recorded that day : {busiest[key][day]}')
            print(f'      odometer km, whole window: {km[key]:.1f}')
            if len(pts) < 2:
                print(f'      fixes in Cassandra      : {len(pts)}'
                      '   <- nothing to validate against')
                continue
            pts.sort(key=lambda p: p[1])
            coords = [p[0] for p in pts]
            path = sum(metres(a, b) for a, b in zip(coords, coords[1:]))
            lons = [c[0] for c in coords]
            lats = [c[1] for c in coords]
            extent = metres((min(lons), min(lats)), (max(lons), max(lats)))
            speeds = [p[2] for p in pts if p[2] is not None]
            hops = [metres(a, b) for a, b in zip(coords, coords[1:])]
            far = sum(1 for h in hops if h > 25)
            print(f'      fixes in Cassandra      : {len(pts)}')
            print(f'      distinct coordinates    : {len(set(coords))}')
            print(f'      path length             : {path/1000.0:.2f} km')
            print(f'      extent (bounding box)   : {extent/1000.0:.3f} km')
            print(f'      hops over 25 m          : {far} of {len(hops)}')
            if speeds:
                print(f'      speed range             : {min(speeds):.1f} '
                      f'to {max(speeds):.1f}')
            runs = billing.get(key, '').lower() == 'running'
            if extent > 2000 and far > 50 and runs:
                verdict = 'DRIVES and billing=running — use this one'
            elif extent > 2000 and far > 50:
                verdict = (f'drives, but billing='
                           f'{billing.get(key) or "NOT REGISTERED"} — the '
                           f'route will reject it')
            elif extent > 2000:
                verdict = 'moves, but position latches between updates'
            elif extent < 200:
                verdict = 'stationary; drift only'
            else:
                verdict = 'local movement only'
            print(f'      -> {verdict}')
            verdicts.append((key, label, verdict, extent, far))

    print('\n' + '=' * 74)
    print('VERDICT')
    print('=' * 74)
    best = [v for v in verdicts if v[2].startswith('DRIVES and billing')]
    if best:
        key, label, _v, _e, _f = best[0]
        print(f'   Validate against unit {key} on {label}:')
        print(f'\n     python scripts/stop_signal.py --imei {key} \\')
        print(f'         --from {label} --to {label}')
        print(f'     python scripts/visit_runs.py --imei {key} \\')
        print(f'         --from {label} --to {label}')
        print('\n   A real driving day is the case a 25 m radius could damage,')
        print('   by merging a crawl through traffic into one fake stop. That')
        print('   is what we need to see before building anything.')
    elif verdicts:
        print('   No candidate drives far enough to settle the radius question.')
        print('   If the odometer in section 1 shows real kilometres but every')
        print('   extent here is small, the trips table and the position store')
        print('   disagree — and that is a bigger problem than B4, because the')
        print('   Trips report is already quoting those odometer numbers to')
        print('   customers.')
    else:
        print('   No candidate had fixes on its busiest trip day. The trips')
        print('   table and the position store may not cover the same period.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
