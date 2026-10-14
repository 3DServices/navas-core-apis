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


def reading(snapshot=None, ago=timedelta(minutes=5), unread=False, imei='x', name=None):
    return {'imei': imei, 'name': name, 'snapshot': snapshot,
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


def at(hour, minute=0, day=12):
    return datetime(2026, 10, day, hour, minute)


def cross(imei, zone, kind, when):
    return {'imei': imei, 'zone': zone, 'type': kind, 'at': when}


zones = [
    {'name': 'Depot', 'ring': SQUARE, 'shape': 'polygon', 'category': 'depot'},
    {'name': 'Yard', 'ring': SQUARE, 'shape': 'circle', 'category': 'restricted'},
    {'name': 'Route', 'ring': SQUARE, 'shape': 'line'},     # corridor: no presence
    {'name': 'Broken', 'ring': [], 'shape': 'polygon', 'category': 'nonsense'},
]
presence = fs.zone_presence([
    reading(snap(lat=0.5, lng=32.5), imei='a', name='UBA 1'),  # inside two zones
    reading(snap(lat=0.5, lng=32.5), ago=timedelta(days=3)), # silent but placed
    reading(snap(lat=5.0, lng=40.0)),                        # outside
    reading(snap(lat=0.5, lng=32.5), ago=timedelta(days=40)),# too old to place
    reading(None),                                           # no position
], zones, NOW, contains, [
    cross('a', 'depot', 'enter', at(8)),         # zone names match any case
    cross('a', 'Depot', 'exit', at(9, 30)),
    cross('b', 'Yard', 'Exit', at(10)),
    cross('c', 'yard', None, at(11)),            # restricted entry
    cross('d', 'Depot', 'entry', at(22, day=11)),# yesterday's entry...
    cross('d', 'Depot', 'exit', at(2)),          # ...left today: 4 h visit
])
eq('zone count includes every zone', presence['zone_count'], 4)
eq('inside', presence['inside'], 2)
eq('outside', presence['outside'], 1)
eq('not placed', presence['not_placed'], 2)
eq('top zones skip corridors',
   presence['top_zones'], [{'name': 'Depot', 'units': 2}, {'name': 'Yard', 'units': 2}])
eq('entries today', presence['entries_today'], 2)
eq('exits today', presence['exits_today'], 3)
eq('by category', presence['by_category'], {
    'general': {'zones': 2, 'units_inside': 0},       # Route, and Broken's bad value
    'depot': {'zones': 1, 'units_inside': 2},
    'customer': {'zones': 0, 'units_inside': 0},
    'restricted': {'zones': 1, 'units_inside': 2}})
eq('restricted inside now', presence['restricted_inside']['count'], 2)
eq('restricted units are named', presence['restricted_inside']['units'][0],
   {'unit': 'UBA 1', 'zone': 'Yard'})
eq('restricted entries today', presence['restricted_entries_today'], 1)
eq('dwell: visits ended today', presence['dwell_today']['visits'], 2)
eq('dwell: median of 90 and 240 min', presence['dwell_today']['median_minutes'], 165)
eq('dwell: longest', presence['dwell_today']['longest'],
   {'unit': 'd', 'zone': 'Depot', 'minutes': 240})

# ── visits ────────────────────────────────────────────────────────────────
eq('exit without entry is no visit', fs.zone_visits([cross('a', 'Z', 'exit', at(9))]), [])
eq('entry not yet left is no visit', fs.zone_visits([cross('a', 'Z', 'enter', at(9))]), [])
eq('missed exit restarts the visit',
   [(v['entered'], v['left']) for v in fs.zone_visits([
       cross('a', 'Z', 'enter', at(8)), cross('a', 'Z', 'enter', at(9)),
       cross('a', 'Z', 'exit', at(10))])],
   [(at(9), at(10))])
eq('units and zones pair separately', len(fs.zone_visits([
    cross('a', 'Z', 'enter', at(8)), cross('b', 'Z', 'exit', at(9)),
    cross('a', 'Y', 'exit', at(9)), cross('a', 'Z', 'exit', at(10))])), 1)
eq('no visits', fs.dwell([], at(0)),
   {'visits': 0, 'median_minutes': None, 'longest': None})
eq('visit ended yesterday is not today',
   fs.dwell([cross('a', 'Z', 'enter', at(8, day=11)),
             cross('a', 'Z', 'exit', at(9, day=11))], at(0))['visits'], 0)


# -- units_by_zone: which vehicle is in which geofence, by name (Waswa) ------

def box(lat0, lng0, lat1, lng1):
    """A ring the test 'contains' reads as a box: [[lng, lat] corners]."""
    return [[lng0, lat0], [lng1, lat0], [lng1, lat1], [lng0, lat1]]


def in_box(lat, lng, ring):
    lngs = [p[0] for p in ring]
    lats = [p[1] for p in ring]
    return min(lats) <= lat <= max(lats) and min(lngs) <= lng <= max(lngs)


ZONES = [
    {'name': 'Head Office', 'ring': box(0.30, 32.50, 0.40, 32.60),
     'shape': 'circle', 'category': 'depot'},
    {'name': 'Quarry', 'ring': box(1.00, 33.00, 1.10, 33.10),
     'shape': 'polygon', 'category': 'restricted'},
    {'name': 'Jinja Road', 'ring': box(0.30, 32.50, 0.40, 32.60),
     'shape': 'line', 'category': 'general'},
]
placed = fs.units_by_zone([
    reading(snap(0.35, 32.55), name='UBJ 916W'),
    reading(snap(1.05, 33.05), name='UAJ 712X'),
    reading(snap(0.90, 31.00), name='UBF 364U'),
    reading(None, ago=None, name='UAY 114Z'),
    reading(snap(0.35, 32.55), ago=timedelta(days=40), name='UAX 391Z'),
], ZONES, NOW, in_box)
eq('a unit in a circle is inside it', placed['zones']['Head Office']['inside'], ['UBJ 916W'])
eq('a unit in a restricted zone is named', placed['zones']['Quarry']['inside'], ['UAJ 712X'])
eq('a route is "on route", never "inside"', placed['zones']['Jinja Road'],
   {'inside': [], 'on_route': ['UBJ 916W']})
eq('a unit in no zone is outside', placed['outside'], ['UBF 364U'])
eq('no position, or a month-old one, is not placed',
   placed['not_placed'], ['UAY 114Z', 'UAX 391Z'])


if __name__ == '__main__':
    failed = [r for r in RESULTS if not r[1]]
    for name, ok, detail in RESULTS:
        print('%s  %s%s' % ('PASS' if ok else 'FAIL', name,
                            '' if ok else '  -- ' + detail))
    print('\n%d passed, %d failed' % (len(RESULTS) - len(failed), len(failed)))
    sys.exit(1 if failed else 0)
