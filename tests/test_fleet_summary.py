# -*- coding: utf-8 -*-
"""Tests for endpoints/fleet_summary.py

fleet_summary.py is pure, so it imports directly -- no Flask, no Redis, no
Cassandra.

Run:  python tests/test_fleet_summary.py
"""

import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'endpoints'))

import fleet_summary as fs                                # noqa: E402

RESULTS = []


def check(name, ok, detail=''):
    RESULTS.append((name, bool(ok), detail))


def eq(name, got, want):
    check(name, got == want, 'got %r, want %r' % (got, want))


NOW = datetime(2026, 10, 12, 12, 0, 0)


def snap(lat=0.3476, lng=32.5825, speed=0, motion='', ignition=None, sats=None):
    s = {'data_latitude': lat, 'data_longitude': lng, 'speed_log': speed,
         'motion_state': motion}
    if ignition is not None:
        s['iginition'] = ignition
    if sats is not None:
        s['data_connected_satelites'] = sats
    return s


def reading(snapshot=None, ago=timedelta(minutes=5), unread=False):
    return {'imei': 'x', 'snapshot': snapshot,
            'seen': None if ago is None else NOW - ago, 'unread': unread}


# ── motion ────────────────────────────────────────────────────────────────
eq('motion_state wins over speed', fs.motion(snap(speed=60, motion='Parked')), 'parked')
eq('idle text', fs.motion(snap(motion='idling')), 'idling')
eq('driving text', fs.motion(snap(motion='Driving')), 'moving')
eq('speed >= 5 moves', fs.motion(snap(speed=5)), 'moving')
eq('crawl idles', fs.motion(snap(speed=2)), 'idling')
eq('stationary, ignition on', fs.motion(snap(ignition='1')), 'idling')
eq('stationary, ignition off', fs.motion(snap(ignition='0')), 'parked')
eq('stationary, no ignition', fs.motion(snap()), 'parked')

# ── classify ──────────────────────────────────────────────────────────────
eq('fresh snapshot', fs.classify(reading(snap(speed=40)), NOW), 'moving')
eq('61 minutes is silent',
   fs.classify(reading(snap(speed=40), ago=timedelta(minutes=61)), NOW), 'silent')
eq('60 minutes is not', fs.classify(reading(snap(), ago=timedelta(minutes=60)), NOW), 'parked')
eq('never seen is silent', fs.classify(reading(None, ago=None), NOW), 'silent')
eq('failed read is unread, not silent',
   fs.classify(reading(None, ago=None, unread=True), NOW), 'unread')
eq('heartbeat without position', fs.classify(reading(None), NOW), 'no_position')

# ── silent ages ───────────────────────────────────────────────────────────
eq('under a day', fs.silent_age(NOW - timedelta(hours=3), NOW), 'under_day')
eq('three days', fs.silent_age(NOW - timedelta(days=3), NOW), 'up_to_week')
eq('a month', fs.silent_age(NOW - timedelta(days=30), NOW), 'over_week')
eq('never', fs.silent_age(None, NOW), 'never')

# ── fleet status ──────────────────────────────────────────────────────────
fleet = fs.fleet_status([
    reading(snap(speed=50, sats=9)),                        # moving
    reading(snap(motion='idle', sats=3)),                   # idling, weak
    reading(snap(lat=0, lng=0)),                            # parked, no fix: weak
    reading(None),                                          # no_position: weak
    reading(snap(), ago=timedelta(hours=5)),                # silent, under a day
    reading(snap(), ago=timedelta(days=10)),                # silent, over a week
    reading(None, ago=None),                                # silent, never
    reading(None, ago=None, unread=True),                   # unread
], NOW)
eq('counts', fleet['counts'], {'moving': 1, 'idling': 1, 'parked': 1,
                               'no_position': 1, 'silent': 3, 'unread': 1})
eq('silent ages', fleet['silent_ages'],
   {'under_day': 1, 'up_to_week': 0, 'over_week': 1, 'never': 1})
eq('weak gps (missing satellites is not weak)', fleet['weak_gps'], 3)
eq('reporting now', fleet['reporting_now'], 4)
eq('total', fleet['total'], 8)
eq('empty fleet', fs.fleet_status([], NOW)['total'], 0)

# ── zones ─────────────────────────────────────────────────────────────────
# A square around (0.5, 32.5) as [lng, lat] pairs, and a simple contains().
SQUARE = [[32.0, 0.0], [33.0, 0.0], [33.0, 1.0], [32.0, 1.0]]


def contains(lat, lng, ring):
    xs = [p[0] for p in ring]
    ys = [p[1] for p in ring]
    return min(xs) <= lng <= max(xs) and min(ys) <= lat <= max(ys)


zones = [
    {'name': 'Depot', 'ring': SQUARE, 'shape': 'polygon'},
    {'name': 'Yard', 'ring': SQUARE, 'shape': 'circle'},
    {'name': 'Route', 'ring': SQUARE, 'shape': 'line'},     # corridor: no presence
    {'name': 'Broken', 'ring': [], 'shape': 'polygon'},
]
presence = fs.zone_presence([
    reading(snap(lat=0.5, lng=32.5)),                        # inside two zones
    reading(snap(lat=0.5, lng=32.5), ago=timedelta(days=3)), # silent but placed
    reading(snap(lat=5.0, lng=40.0)),                        # outside
    reading(snap(lat=0.5, lng=32.5), ago=timedelta(days=40)),# too old to place
    reading(None),                                           # no position
], zones, NOW, contains, ['enter', 'exit', 'Exit', None])
eq('zone count includes every zone', presence['zone_count'], 4)
eq('inside', presence['inside'], 2)
eq('outside', presence['outside'], 1)
eq('not placed', presence['not_placed'], 2)
eq('top zones skip corridors',
   presence['top_zones'], [{'name': 'Depot', 'units': 2}, {'name': 'Yard', 'units': 2}])
eq('entries today', presence['entries_today'], 2)
eq('exits today', presence['exits_today'], 2)


if __name__ == '__main__':
    failed = [r for r in RESULTS if not r[1]]
    for name, ok, detail in RESULTS:
        print('%s  %s%s' % ('PASS' if ok else 'FAIL', name,
                            '' if ok else '  -- ' + detail))
    print('\n%d passed, %d failed' % (len(RESULTS) - len(failed), len(failed)))
    sys.exit(1 if failed else 0)
