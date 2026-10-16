#!/usr/bin/env python3
"""
stop_signal.py — what actually distinguishes a stopped vehicle from a moving one?

Why this exists
---------------
visit_runs.py printed "exact equality holds; no radius needed" for
867556044727322 and its own radius table contradicted it: a 10 m radius
collapsed 395 runs into 20. The jitter test was the wrong test — A-B-A catches
oscillation between two points and is blind to a random walk, which is what GPS
drift looks like. So 376 "distinct positions" on 12-13 August may be a parked
vehicle whose fix wandered, not a journey.

That distinction decides whether trip history can answer dwell time at all:

  * if they are drift, exact-match run collapse reports 376 one-sample
    "visits" during what was really one long stop. Dwell becomes noise.
  * if they are a journey, collapsing them with a radius erases a real trip.

Guessing from coordinate equality is the wrong instrument either way, because
the device already reports what we are trying to infer: speed_log. This
measures the three signals and says which one to build on.

  1. CONSECUTIVE DISTANCE   how far apart successive fixes are. A driving
     vehicle sampled each minute moves hundreds of metres. A mass of pairs
     under ~20 m is drift.

  2. SPEED                  what speed_log reports, and whether speed > 0
     coincides with large consecutive distances. If it does, speed is a
     trustworthy stop signal and the whole radius question disappears.

  3. PATH VERSUS EXTENT     per day, the summed path length against the
     bounding-box diagonal. A vehicle that drives 40 km in a straight-ish
     line has a path close to its extent. A drifting stationary one
     accumulates kilometres of path inside a 30 m box. The ratio tells them
     apart with no threshold to choose.

Read-only. Measures; decides nothing.

Usage:
    python scripts/stop_signal.py --imei 867556044727322 --from 12-08-2025 --to 20-08-2025
    python scripts/stop_signal.py --imei 862846042652860 --from 12-08-2025 --to 20-08-2025
"""

import argparse
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from math import atan2, cos, radians, sin, sqrt

sys.path.insert(0, '.')
from config import DB_LINK                              # noqa: E402

RAW = ("SELECT data_longitude, data_latitude, record_timestamp, "
       "local_system_datestamp, local_system_timestamp, speed_log "
       "FROM dll_location_registry_by_record_ts "
       "WHERE data_device_imei = ? AND local_system_datestamp = ?")

BUCKETS = ((0.0, 'exactly 0 m'), (5.0, 'under 5 m'), (10.0, '5 - 10 m'),
           (25.0, '10 - 25 m'), (50.0, '25 - 50 m'), (100.0, '50 - 100 m'),
           (500.0, '100 - 500 m'), (2000.0, '500 m - 2 km'),
           (float('inf'), 'over 2 km'))


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


def metres(a, b):
    lon1, lat1 = radians(a[0]), radians(a[1])
    lon2, lat2 = radians(b[0]), radians(b[1])
    h = (sin((lat2 - lat1) / 2) ** 2
         + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2)
    return 6371000.0 * 2 * atan2(sqrt(h), sqrt(1 - h))


def bucket(d):
    for limit, label in BUCKETS:
        if d <= limit:
            return label
    return BUCKETS[-1][1]


def bar(n, total, width=28):
    filled = int(round(width * n / total)) if total else 0
    return '#' * filled + '.' * (width - filled)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--imei', required=True)
    ap.add_argument('--from', dest='from_date', default='12-08-2025')
    ap.add_argument('--to', dest='to_date', default='20-08-2025')
    args = ap.parse_args()
    imei = ''.join(str(args.imei).split())

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
        fixes = []
        for day in days(args.from_date, args.to_date):
            try:
                rows = list(session.execute(stmt, (imei, day)))
            except Exception as error:                  # noqa: BLE001
                print(f'   {day}: ERROR {str(error)[:50]}')
                continue
            for r in rows:
                lon, lat = num(r.data_longitude), num(r.data_latitude)
                if lon is None or lat is None or (lon == 0 and lat == 0):
                    continue
                if r.record_timestamp is None:
                    continue
                fixes.append({'coord': (lon, lat), 'at': r.record_timestamp,
                              'day': r.local_system_datestamp,
                              'speed': num(r.speed_log)})
    if len(fixes) < 2:
        print('!! not enough fixes. Use days the overlap finder found.')
        return 1
    fixes.sort(key=lambda f: f['at'])

    print(f'unit {imei}, {args.from_date} to {args.to_date}')
    print(f'fixes: {len(fixes)}\n')

    # ── 1. consecutive distance ────────────────────────────────────────────
    print('=' * 70)
    print('1. DISTANCE BETWEEN SUCCESSIVE FIXES')
    print('=' * 70)
    pairs = []
    for a, b in zip(fixes, fixes[1:]):
        gap = (b['at'] - a['at']).total_seconds()
        pairs.append((metres(a['coord'], b['coord']), gap, a, b))
    hist = Counter(bucket(d) for d, _, _, _ in pairs)
    total = len(pairs)
    for _, label in BUCKETS:
        n = hist.get(label, 0)
        print(f'   {label:<14} {n:>6}  {100.0*n/total:>5.1f}%  {bar(n, total)}')
    close = sum(n for lbl, n in hist.items()
                if lbl in ('exactly 0 m', 'under 5 m', '5 - 10 m',
                           '10 - 25 m'))
    print(f'\n   within 25 m of the previous fix : {close} of {total} '
          f'({100.0*close/total:.1f}%)')
    if close > 0.8 * total:
        print('   -> Most successive fixes barely move. This unit is mostly')
        print('      stationary and its distinct coordinates are drift.')

    # ── 2. speed ───────────────────────────────────────────────────────────
    print('\n' + '=' * 70)
    print('2. WHAT speed_log SAYS')
    print('=' * 70)
    agree = checked = 0
    speeds = [f['speed'] for f in fixes]
    missing = sum(1 for s in speeds if s is None)
    known = [s for s in speeds if s is not None]
    print(f'   fixes with no speed value : {missing}')
    if not known:
        print('   !! speed_log is empty for this unit. It cannot be the stop')
        print('      signal; the design must fall back to a radius.')
    else:
        zero = sum(1 for s in known if s == 0)
        low = sum(1 for s in known if 0 < s <= 5)
        moving = sum(1 for s in known if s > 5)
        print(f'   speed = 0                 : {zero:>6}  '
              f'{100.0*zero/len(known):>5.1f}%')
        print(f'   0 < speed <= 5            : {low:>6}  '
              f'{100.0*low/len(known):>5.1f}%')
        print(f'   speed > 5                 : {moving:>6}  '
              f'{100.0*moving/len(known):>5.1f}%')
        print(f'   max speed seen            : {max(known):.1f}')

        # Does speed predict movement? A plain agreement rate cannot answer
        # this: ~99% of pairs are parked-and-reporting-zero, so any metric
        # averaged over all pairs scores ~99% while being blind to the only
        # case that matters. The first version of this script made exactly
        # that mistake and declared speed trustworthy. So the classes are
        # reported separately, and nothing is averaged across them.
        moved = [(d, a) for d, _, a, _ in pairs
                 if a['speed'] is not None and d > 25]
        still = [(d, a) for d, _, a, _ in pairs
                 if a['speed'] is not None and d <= 25]
        checked = len(moved) + len(still)
        print(f'\n   pairs that MOVED (> 25 m)  : {len(moved)}')
        if moved:
            for label, test in (('speed = 0        ', lambda s: s == 0),
                                ('0 < speed <= 5   ', lambda s: 0 < s <= 5),
                                ('speed > 5        ', lambda s: s > 5)):
                n = sum(1 for _, a in moved if test(a['speed']))
                print(f'      {label} : {n:>6}  {100.0*n/len(moved):>5.1f}%')
        print(f'\n   pairs that did NOT move    : {len(still)}')
        if still:
            for label, test in (('speed = 0        ', lambda s: s == 0),
                                ('0 < speed <= 5   ', lambda s: 0 < s <= 5),
                                ('speed > 5        ', lambda s: s > 5)):
                n = sum(1 for _, a in still if test(a['speed']))
                print(f'      {label} : {n:>6}  {100.0*n/len(still):>5.1f}%')

        # The question that decides the design: when speed is non-zero, is
        # the vehicle actually moving?
        nonzero = [(d, a) for d, a in moved + still if a['speed'] > 0]
        useful = sum(1 for d, _ in nonzero if d > 25)
        if nonzero:
            precision = 100.0 * useful / len(nonzero)
            print(f'\n   non-zero speed readings    : {len(nonzero)}')
            print(f'   of those, actually moving  : {useful} '
                  f'({precision:.1f}%)')
            recall = (100.0 * sum(1 for d, a in moved if a['speed'] > 0)
                      / len(moved)) if moved else 0
            print(f'   moving pairs speed caught  : {recall:.1f}%')
            agree = useful
            if precision > 80 and recall > 80:
                print('\n   -> speed_log predicts movement in both directions.')
                print('      Use it as the stop signal: no radius, no tuning.')
            else:
                print('\n   -> speed_log is NOT a usable movement signal here.')
                print(f'      {100.0 - precision:.0f}% of non-zero readings')
                print('      happen while the vehicle is stationary. Build on')
                print('      consecutive distance instead, with a threshold')
                print('      taken from the empty band in section 1.')

    # ── 3. path versus extent, per day ─────────────────────────────────────
    print('\n' + '=' * 70)
    print('3. PATH LENGTH VERSUS HOW FAR IT ACTUALLY WENT')
    print('=' * 70)
    by_day = defaultdict(list)
    for f in fixes:
        by_day[f['day']].append(f)
    print(f'   {"day":<12} {"fixes":>6} {"path km":>9} {"extent km":>10} '
          f'{"ratio":>7}  reading')
    print('   ' + '-' * 64)
    for day in sorted(by_day, key=lambda d: datetime.strptime(d, '%d-%m-%Y')):
        rows = by_day[day]
        if len(rows) < 2:
            continue
        path = sum(metres(a['coord'], b['coord'])
                   for a, b in zip(rows, rows[1:]))
        lons = [r['coord'][0] for r in rows]
        lats = [r['coord'][1] for r in rows]
        extent = metres((min(lons), min(lats)), (max(lons), max(lats)))
        ratio = (path / extent) if extent > 1 else float('inf')
        if extent < 100:
            reading = 'stationary (drift)'
        elif ratio > 20:
            reading = 'drift or idling'
        elif ratio > 3:
            reading = 'local trips'
        else:
            reading = 'a journey'
        print(f'   {day:<12} {len(rows):>6} {path/1000.0:>9.2f} '
              f'{extent/1000.0:>10.3f} '
              f'{("inf" if ratio == float("inf") else f"{ratio:.1f}"):>7}  '
              f'{reading}')

    print('\n' + '=' * 70)
    print('WHAT THIS MEANS FOR B4')
    print('=' * 70)
    if checked and agree and agree > 0.8 * max(1, sum(
            1 for d, _, a, _ in pairs if a['speed'] is not None
            and a['speed'] > 0)):
        print('   Build the stop detector on speed_log, not on coordinates:')
        print('     * speed = 0 for consecutive fixes  -> one stop, with')
        print('       arrival, departure and dwell')
        print('     * speed > 0                        -> a moving fix, kept')
        print('       in sequence')
        print('   No radius, no coordinate equality, nothing to tune. Drift')
        print('   while stopped stops mattering, because the device already')
        print('   told us it was stopped.')
    else:
        print('   speed_log cannot carry this alone. Fall back to grouping')
        print('   consecutive fixes within a radius chosen from section 1,')
        print('   and split a group when section 1 shows a long sample gap.')
    print('\n   Either way, exact coordinate equality is the wrong rule and')
    print('   visit_runs.py\'s verdict line should not be relied on.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
