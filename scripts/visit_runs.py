#!/usr/bin/env python3
"""
visit_runs.py — can consecutive-run collapse actually answer dwell time?

Trip history is supposed to tell a customer how long a vehicle sat somewhere.
The legacy rule cannot: one row per distinct coordinate, stamped with the
latest time, so an 09:00-17:00 stop is a single fix at 17:00 and the eight
hours are gone.

The replacement is to collapse CONSECUTIVE runs at the same position instead
of deduplicating globally, giving arrival, departure and duration per visit.
That design rests on one assumption about the data, and this measures it
rather than trusting it:

    a parked tracker repeats the SAME coordinate, bit for bit

Three raw rows suggested it. Three rows is not evidence. If a stationary unit
actually oscillates between two nearby fixes — A, B, A, B — then exact-equality
grouping shatters one eight-hour visit into hundreds of one-minute runs and
every dwell figure it produces is nonsense.

So this reports four things:

  1. how many runs exact equality produces, against the legacy count
  2. JITTER: single-sample runs whose neighbours share one coordinate (A,B,A),
     and how far apart A and B are in metres — the oscillation signature
  3. what a radius of 10, 25 and 50 m would produce instead, so the threshold
     is chosen from the data if one is needed at all
  4. TIME GAPS inside runs: a unit reporting from the same spot either side of
     a six-hour silence is probably two visits, not one. If these are common,
     the design needs a gap rule as well as a position rule.

It also prints the longest visits with arrival and departure in local time, so
the output can be sanity-checked against what a vehicle plausibly did.

Read-only. Decides nothing; measures what the decision needs.

Usage:
    python scripts/visit_runs.py --imei 867556044727322 --from 12-08-2025 --to 20-08-2025
    python scripts/visit_runs.py --imei 862846042652860 --from 12-08-2025 --to 20-08-2025
"""

import argparse
import sys
from datetime import datetime, timedelta
from math import atan2, cos, radians, sin, sqrt

sys.path.insert(0, '.')
from config import DB_LINK                              # noqa: E402

RAW = ("SELECT data_longitude, data_latitude, record_timestamp, "
       "local_system_datestamp, local_system_timestamp, speed_log "
       "FROM dll_location_registry_by_record_ts "
       "WHERE data_device_imei = ? AND local_system_datestamp = ?")

RADII = (10.0, 25.0, 50.0)
GAP_MINUTES = 30


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
    """Great-circle distance between two (lon, lat) pairs."""
    lon1, lat1 = radians(a[0]), radians(a[1])
    lon2, lat2 = radians(b[0]), radians(b[1])
    dlon, dlat = lon2 - lon1, lat2 - lat1
    h = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 6371000.0 * 2 * atan2(sqrt(h), sqrt(1 - h))


def human(seconds):
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f'{h}h {m:02d}m'
    if m:
        return f'{m}m {s:02d}s'
    return f'{s}s'


def runs_exact(fixes):
    """Consecutive fixes sharing a coordinate, exactly."""
    out = []
    for f in fixes:
        if out and out[-1]['coord'] == f['coord']:
            out[-1]['fixes'].append(f)
        else:
            out.append({'coord': f['coord'], 'fixes': [f]})
    return out


def runs_radius(fixes, limit):
    """Consecutive fixes within `limit` metres of the run's first fix."""
    out = []
    for f in fixes:
        if out and metres(out[-1]['coord'], f['coord']) <= limit:
            out[-1]['fixes'].append(f)
        else:
            out.append({'coord': f['coord'], 'fixes': [f]})
    return out


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
                fixes.append({
                    'coord': (lon, lat),
                    'at_utc': r.record_timestamp,
                    'day': r.local_system_datestamp,
                    'clock': r.local_system_timestamp,
                    'speed': num(r.speed_log),
                })

    if not fixes:
        print('!! no fixes in this window. Use days the overlap finder found.')
        return 1

    fixes.sort(key=lambda f: f['at_utc'])
    exact = runs_exact(fixes)
    legacy = len({f['coord'] for f in fixes})

    print(f'unit {imei}, {args.from_date} to {args.to_date}\n')
    print('=' * 68)
    print('1. HOW MANY ROWS EACH RULE PRODUCES')
    print('=' * 68)
    print(f'   raw fixes                       : {len(fixes)}')
    print(f'   legacy: distinct coords, window : {legacy}')
    print(f'   runs: consecutive, exact match  : {len(exact)}')
    extra = len(exact) - legacy
    print(f'\n   run collapse returns {extra:+d} row(s) versus the legacy rule.')
    print('   More is expected and is the point: a place visited twice is two')
    print('   rows instead of one.')

    print('\n' + '=' * 68)
    print('2. JITTER — does a parked unit hold one coordinate?')
    print('=' * 68)
    singles = [i for i, r in enumerate(exact) if len(r['fixes']) == 1]
    oscillating, distances = 0, []
    for i in singles:
        if 0 < i < len(exact) - 1:
            before, after = exact[i - 1]['coord'], exact[i + 1]['coord']
            if before == after:
                oscillating += 1
                distances.append(metres(before, exact[i]['coord']))
    print(f'   runs of exactly one sample      : {len(singles)}')
    print(f'   of those, A-B-A oscillations    : {oscillating}')
    if distances:
        distances.sort()
        mid = distances[len(distances) // 2]
        print(f'   A-to-B distance, median         : {mid:.1f} m')
        print(f'   A-to-B distance, max            : {max(distances):.1f} m')
    share = 100.0 * oscillating / len(exact) if exact else 0
    print(f'   oscillations as share of runs   : {share:.1f}%')
    if share < 5:
        print('\n   -> Low, BUT THIS TEST IS WEAK. A-B-A catches a tracker')
        print('      oscillating between two points. It cannot see a random')
        print('      walk: drift that wanders A-B-C-D and never returns scores')
        print('      0% here. Read section 3 before believing this line — if a')
        print('      10 m radius collapses most of the runs, the positions are')
        print('      drifting and exact equality is NOT sufficient. Use')
        print('      scripts/stop_signal.py, which measures consecutive')
        print('      distance and speed instead of guessing from equality.')
    else:
        print('\n   -> HIGH. Exact equality fragments stationary periods. The')
        print('      grouping needs a radius; see section 3 for the value.')

    print('\n' + '=' * 68)
    print('3. WHAT A RADIUS WOULD GIVE INSTEAD')
    print('=' * 68)
    print(f'   {"rule":<22} {"rows":>7}   {"vs exact":>9}')
    print('   ' + '-' * 42)
    print(f'   {"exact match":<22} {len(exact):>7}   {"-":>9}')
    for limit in RADII:
        grouped = runs_radius(fixes, limit)
        print(f'   {"within " + str(int(limit)) + " m":<22} '
              f'{len(grouped):>7}   {len(grouped) - len(exact):>+9d}')
    print('\n   A radius that collapses far more rows than exact match is')
    print('   merging genuinely different places. One that changes almost')
    print('   nothing is unnecessary complexity.')

    print('\n' + '=' * 68)
    print(f'4. TIME GAPS INSIDE RUNS (> {GAP_MINUTES} min between samples)')
    print('=' * 68)
    gappy, worst = 0, 0.0
    for r in exact:
        stamps = [f['at_utc'] for f in r['fixes']]
        for a, b in zip(stamps, stamps[1:]):
            gap = (b - a).total_seconds() / 60.0
            if gap > GAP_MINUTES:
                gappy += 1
                worst = max(worst, gap)
                break
    print(f'   runs containing such a gap      : {gappy} of {len(exact)}')
    if gappy:
        print(f'   longest gap inside one run      : {human(worst * 60)}')
        print('\n   -> A unit reporting from one spot either side of a silence')
        print('      that long is probably two visits. The design needs a gap')
        print('      rule: split a run when the samples pause for longer than')
        print('      the threshold.')
    else:
        print('\n   -> None. Position alone is enough to bound a visit.')

    print('\n' + '=' * 68)
    print('5. THE LONGEST VISITS, TO EYEBALL AGAINST REALITY')
    print('=' * 68)
    sized = []
    for r in exact:
        stamps = [f['at_utc'] for f in r['fixes']]
        sized.append((( stamps[-1] - stamps[0]).total_seconds(), r))
    sized.sort(key=lambda p: p[0], reverse=True)
    print(f'   {"dwell":>9}  {"samples":>7}  {"arrived (local)":<22} departed')
    print('   ' + '-' * 60)
    for seconds, r in sized[:8]:
        first, last = r['fixes'][0], r['fixes'][-1]
        print(f'   {human(seconds):>9}  {len(r["fixes"]):>7}  '
              f'{first["day"]} {first["clock"]:<10} '
              f'{last["day"]} {last["clock"]}')
    stops = [s for s, _ in sized if s >= 300]
    print(f'\n   runs of 5 minutes or more       : {len(stops)}')
    print(f'   total time accounted as stopped : '
          f'{human(sum(stops))}')
    span = (fixes[-1]['at_utc'] - fixes[0]['at_utc']).total_seconds()
    print(f'   window span covered by fixes    : {human(span)}')
    if span:
        print(f'   stopped share of the window     : '
              f'{100.0 * sum(stops) / span:.0f}%')

    print('\n' + '=' * 68)
    print('VERDICT')
    print('=' * 68)
    if share < 5 and not gappy:
        print('   Consecutive-run collapse on an exact coordinate match is')
        print('   sufficient. B4 is a position rule only — no radius, no gap')
        print('   threshold, no tuning parameter to get wrong later.')
    elif share < 5:
        print('   Exact match is fine for position, but runs span real')
        print('   silences. B4 needs a gap rule and no radius.')
    else:
        print('   Exact match is not sufficient. B4 needs a radius, chosen')
        print('   from section 3, and a gap rule if section 4 found gaps.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
