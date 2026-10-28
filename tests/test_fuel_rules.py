# -*- coding: utf-8 -*-
"""Tests for endpoints/fuel_rules.py (FuelMath).

fuel_rules.py is pure, so it imports directly.

Run:  python tests/test_fuel_rules.py
"""

import os
import sys
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'endpoints'))

import fuel_rules as fr                                   # noqa: E402

RESULTS = []


def check(name, ok, detail=''):
    RESULTS.append((name, bool(ok), detail))


def eq(name, got, want):
    check(name, got == want, 'got %r, want %r' % (got, want))


NOW = datetime(2026, 10, 28, 12, 0)
AT = datetime(2026, 10, 28, 9, 0)

VALID = {
    'device_imei': ' 354002396040196 ',
    'driver_uid': 'd-1',
    'issued_at': '2026-10-28T09:00',
    'litres': '40',
    'unit_price': '5,150',
    'fuel_type': 'Diesel',
    'station_name': '  Shell   Jinja Road ',
    'payment_method': 'fuel_card',
    'full_tank': True,
    'odometer_km': '120450',
    'receipt_number': ' r-00123 ',
}

PROFILE = {'fuel_type': 'diesel', 'tank_capacity_l': 80,
           'baseline_km_per_l': 10, 'tolerance_pct': 20}
DRIVER = {'status': 'active', 'permit_expiry': date(2028, 1, 1)}


def line(start, minutes, step_m, every_s=30, lat=0.3476, lon=32.5825):
    """Fixes from `start` for `minutes`, moving north `step_m` metres per fix."""
    out, t, i = [], start, 0
    end = start + timedelta(minutes=minutes)
    while t <= end:
        out.append({'lat': lat + i * step_m / 111195.0, 'lon': lon, 'at': t,
                    'place': 'Jinja Road'})
        t += timedelta(seconds=every_s)
        i += 1
    return out


def parked(start, minutes, every_s=30, lat=0.3476, lon=32.5825):
    return line(start, minutes, 0, every_s, lat, lon)


def clean_issue(**over):
    data = dict(VALID, **over)
    clean, errors = fr.validate_issue(data, NOW)
    assert not errors, errors
    return clean


# ── validation ────────────────────────────────────────────────────────────
clean, errors = fr.validate_issue(VALID, NOW)
eq('a valid issue has no errors', errors, {})
eq('imei spaces removed', clean['device_imei'], '354002396040196')
eq('issued_at parsed', clean['issued_at'], AT)
eq('price with a thousands comma', clean['unit_price'], 5150.0)
eq('fuel type lower-cased', clean['fuel_type'], 'diesel')
eq('station whitespace collapsed', clean['station_name'], 'Shell Jinja Road')
eq('receipt upper-cased', clean['receipt_number'], 'R-00123')
eq('total = litres x price, whole shillings', clean['total_cost'], 206000.0)
eq('full tank', clean['full_tank'], True)
eq('total rounds to the shilling', fr.total_cost(33.33, 5150), 171650.0)

_, errors = fr.validate_issue({}, NOW)
eq('every required field reported',
   sorted(errors), sorted(['device_imei', 'driver_uid', 'issued_at', 'litres',
                           'unit_price', 'fuel_type', 'station_name',
                           'payment_method']))

clean, errors = fr.validate_issue(dict(VALID, fuel_type=''), NOW, 'petrol')
eq('fuel type taken from the profile', (errors, clean['fuel_type']), ({}, 'petrol'))

for name, over, field in [
        ('zero litres', {'litres': '0'}, 'litres'),
        ('litres not a number', {'litres': 'forty'}, 'litres'),
        ('too many litres', {'litres': '1001'}, 'litres'),
        ('price too low', {'unit_price': '50'}, 'unit_price'),
        ('boolean is not a number', {'litres': True}, 'litres'),
        ('unknown fuel', {'fuel_type': 'kerosene'}, 'fuel_type'),
        ('unknown payment', {'payment_method': 'barter'}, 'payment_method'),
        ('station too short', {'station_name': 'x'}, 'station_name'),
        ('future time', {'issued_at': '2026-10-28T12:30'}, 'issued_at'),
        ('older than 92 days', {'issued_at': '2026-07-01T09:00'}, 'issued_at'),
        ('time will not parse', {'issued_at': '28/10/2026'}, 'issued_at'),
        ('negative odometer', {'odometer_km': '-5'}, 'odometer_km'),
        ('receipt too long', {'receipt_number': 'X' * 61}, 'receipt_number')]:
    _, errors = fr.validate_issue(dict(VALID, **over), NOW)
    check('refused: ' + name, field in errors, repr(errors))

_, errors = fr.validate_issue(dict(VALID, issued_at='2026-10-28T12:05'), NOW)
eq('a phone a few minutes fast is fine', errors, {})
clean, _ = fr.validate_issue(dict(VALID, odometer_km='', receipt_number='', full_tank='no'), NOW)
eq('blank optional fields are None',
   (clean['odometer_km'], clean['receipt_number'], clean['full_tank']), (None, None, False))

# ── profiles ──────────────────────────────────────────────────────────────
clean, errors = fr.validate_profile({'fuel_type': 'petrol', 'tank_capacity_l': '55',
                                     'baseline_km_per_l': '11.5'})
eq('profile valid, default tolerance', (errors, clean['tolerance_pct']), ({}, 20))
for name, over, field in [
        ('no fuel type', {'fuel_type': ''}, 'fuel_type'),
        ('no tank', {'tank_capacity_l': '0'}, 'tank_capacity_l'),
        ('baseline zero', {'baseline_km_per_l': '0'}, 'baseline_km_per_l'),
        ('tolerance too high', {'tolerance_pct': '80'}, 'tolerance_pct'),
        ('tolerance fractional', {'tolerance_pct': '12.5'}, 'tolerance_pct')]:
    _, errors = fr.validate_profile(dict({'fuel_type': 'petrol', 'tank_capacity_l': 55,
                                          'baseline_km_per_l': 11}, **over))
    check('profile refused: ' + name, field in errors, repr(errors))

# ── distance ──────────────────────────────────────────────────────────────
ten_km = line(AT, 100, 50)                 # 201 fixes, 50 m apart = 10 km
km = fr.track_km(ten_km)
check('a 10 km line measures 10 km', abs(km - 10.0) < 0.05, km)
eq('parked jitter is not distance', fr.track_km(parked(AT, 60)), 0.0)
wobble = [dict(p, lat=p['lat'] + (0.00005 if i % 2 else 0)) for i, p in enumerate(parked(AT, 30))]
eq('5 m wobble is not distance', fr.track_km(wobble), 0.0)
jump = line(AT, 10, 50)
jump.insert(5, {'lat': 1.5, 'lon': 33.0, 'at': AT + timedelta(seconds=135), 'place': None})
check('a teleporting bad fix is skipped', abs(fr.track_km(jump) - 1.0) < 0.05,
      fr.track_km(jump))
half = fr.track_km(ten_km, AT, AT + timedelta(minutes=50))
check('distance between two times', abs(half - 5.0) < 0.05, half)

# ── stops ─────────────────────────────────────────────────────────────────
W = fr.STOP_WINDOW
drive_stop_drive = (line(AT - timedelta(minutes=60), 50, 100)
                    + parked(AT - timedelta(minutes=5), 10, lat=0.5)
                    + line(AT + timedelta(minutes=10), 50, 100, lat=0.51))
stop = fr.find_stop(drive_stop_drive, AT - W, AT + W)
check('a 10-minute stop near the time is found', stop is not None)
eq('the stop fix nearest the issue time', stop['at'] if stop else None, AT)
eq('driving all along: no stop', fr.find_stop(line(AT - W, 90, 100), AT - W, AT + W), None)
quiet = [{'lat': 0.5, 'lon': 32.6, 'at': AT - timedelta(minutes=70), 'place': 'Depot'},
         {'lat': 0.50001, 'lon': 32.6, 'at': AT + timedelta(minutes=70), 'place': 'Depot'}]
check('a quiet tracker parked across the window is a stop',
      fr.find_stop(quiet, AT - W, AT + W) is not None)
early = parked(AT - timedelta(hours=3), 10) + line(AT - W, 90, 100, lat=0.6)
eq('a stop long before the window does not count', fr.find_stop(early, AT - W, AT + W), None)

# ── assess ────────────────────────────────────────────────────────────────
FULL_BEFORE = {'issue_uid': 'prev', 'issued_at': AT - timedelta(days=2)}


def trip(km_driven, stop_at_issue=True):
    """Fixes from the previous full tank to after the issue: `km_driven`
    driven, then parked at the station around AT."""
    start = FULL_BEFORE['issued_at']
    minutes = int(km_driven * 1000 / 100 * 0.5)      # 100 m per 30 s fix
    points = line(start, minutes, 100)
    last = points[-1]
    if stop_at_issue:
        points += parked(AT - timedelta(minutes=20), 40, lat=last['lat'])
    return points


def assess(**kw):
    issue = kw.pop('issue', None) or clean_issue()
    base = dict(profile=PROFILE, previous_full=FULL_BEFORE, since_full=[],
                previous_odometer=None, points=trip(400), driver=DRIVER,
                assigned_driver_uid='d-1', nearby_issues=0)
    base.update(kw)
    return fr.assess(issue, **base)


ok = assess()
eq('a normal fill: no flags', ok['flags'], [])
eq('a normal fill: nothing to review', ok['review_state'], 'none')
eq('tracker checked', ok['tracker_state'], 'checked')
check('km since full measured', abs(ok['km_since_full'] - 400) < 1, ok['km_since_full'])
eq('litres since full', ok['litres_since_full'], 40.0)
check('km per litre at a full tank', abs(ok['km_per_l'] - 10.0) < 0.05, ok['km_per_l'])
eq('previous full tank recorded', ok['previous_full_uid'], 'prev')
eq('tracker place stored', ok['tracker_place'], 'Jinja Road')

heavy = assess(points=trip(200))
check('40 L after 200 km at 10 km/L: more than used', 'more_than_used' in heavy['flags'])
eq('a discrepancy opens a review', heavy['review_state'], 'open')
eq('within tolerance plus margin: fine',
   assess(points=trip(300))['flags'], [])          # expected 30 L, allowed 41 L
partials = assess(points=trip(400), since_full=[{'litres': 30}])
check('earlier partial top-ups count towards the fill',
      'more_than_used' in partials['flags'], partials)
eq('partial issue has no km per litre',
   assess(issue=clean_issue(full_tank=False))['km_per_l'], None)

check('over capacity', 'over_capacity' in assess(issue=clean_issue(litres='90'))['flags'])
check('fuel type mismatch',
      'fuel_type_mismatch' in assess(issue=clean_issue(fuel_type='petrol'))['flags'])
driving_through = trip(400, stop_at_issue=False) + line(AT - W, 90, 100, lat=0.7)
check('not stopped at the time', 'not_stopped' in assess(points=driving_through)['flags'])
check('another driver assigned', 'driver_not_assigned' in assess(assigned_driver_uid='d-9')['flags'])
eq('no assignment at the time is not a flag', assess(assigned_driver_uid=None)['flags'], [])
check('suspended driver',
      'driver_not_allowed' in assess(driver={'status': 'suspended',
                                             'permit_expiry': date(2028, 1, 1)})['flags'])
check('permit expired on the issue date',
      'driver_not_allowed' in assess(driver={'status': 'active',
                                             'permit_expiry': date(2026, 10, 1)})['flags'])
check('possible duplicate', 'possible_duplicate' in assess(nearby_issues=1)['flags'])

no_profile = assess(profile=None)
eq('no profile: notice only', (no_profile['flags'], no_profile['review_state']),
   (['no_profile'], 'none'))
down = assess(points=None)
eq('positions unreadable: notice, not checked',
   (down['tracker_state'], 'tracker_unavailable' in down['flags'], down['km_since_full']),
   ('unavailable', True, None))
nothing = assess(points=[])
eq('tracker silent: no data notice', (nothing['tracker_state'], nothing['flags']),
   ('no_data', ['no_tracker_data']))
first = assess(previous_full=None)
eq('first full tank: notice', first['flags'], ['first_full_tank'])
long_ago = assess(previous_full={'issue_uid': 'old', 'issued_at': AT - timedelta(days=30)})
eq('span too long: notice', long_ago['flags'], ['span_too_long'])

prev_odo = {'issued_at': FULL_BEFORE['issued_at'], 'odometer_km': 120050}
eq('odometer agrees with the tracker (400 km)',
   assess(previous_odometer=prev_odo)['flags'], [])
check('odometer backwards',
      'odometer_backwards' in assess(previous_odometer=dict(prev_odo, odometer_km=130000))['flags'])
check('odometer 200 km more than the tracker',
      'odometer_mismatch' in assess(previous_odometer=dict(prev_odo, odometer_km=119850))['flags'])
older_odo = {'issued_at': AT - timedelta(days=10), 'odometer_km': 100000}
eq('previous reading before the positions read: not compared',
   assess(previous_odometer=older_odo)['flags'], [])

# ── reviews ───────────────────────────────────────────────────────────────
eq('review an open issue', fr.review_refusal('open', 'explained', False), None)
eq('re-review is allowed', fr.review_refusal('explained', 'confirmed_loss', False), None)
check('nothing to review', fr.review_refusal('none', 'explained', False))
check('unknown outcome', fr.review_refusal('open', 'ignore', False))
check('voided issue', fr.review_refusal('open', 'explained', True))
eq('notices alone open nothing', fr.review_state_for(['no_profile', 'first_full_tank']), 'none')

# ── public shape ──────────────────────────────────────────────────────────
row = dict(clean_issue(), **ok)
row.update(issue_uid='i-1', flags='not_stopped,no_profile',
           receipt_file='i-1_abc.jpg', voided_at=None, created_at=NOW,
           driver_name='Okello John', review_state='open')
out = fr.public_issue(row)
eq('flags expanded with kind and message',
   [(f['code'], f['kind']) for f in out['flags']],
   [('not_stopped', 'discrepancy'), ('no_profile', 'notice')])
eq('receipt file name not exposed', ('receipt_file' in out, out['has_receipt']), (False, True))
eq('issued_at as ISO', out['issued_at'], '2026-10-28T09:00:00')
eq('tracker nested', out['tracker']['state'], 'checked')

# ── summary ───────────────────────────────────────────────────────────────
issues = [
    {'device_imei': 'A', 'driver_uid': 'd-1', 'driver_name': 'Okello', 'litres': 40,
     'total_cost': 200000, 'full_tank': True, 'km_per_l': 8, 'km_since_full': 320,
     'litres_since_full': 40, 'flags': 'more_than_used', 'review_state': 'open'},
    {'device_imei': 'A', 'driver_uid': 'd-2', 'driver_name': 'Achen', 'litres': 20,
     'total_cost': 100000, 'full_tank': False, 'km_per_l': None, 'km_since_full': 100,
     'litres_since_full': 20, 'flags': '', 'review_state': 'none'},
    {'device_imei': 'B', 'driver_uid': 'd-2', 'driver_name': 'Achen', 'litres': 30,
     'total_cost': 156000, 'full_tank': True, 'km_per_l': None, 'km_since_full': None,
     'litres_since_full': None, 'flags': 'first_full_tank', 'review_state': 'none'},
]
s = fr.summarise(issues, {'A': PROFILE})
a = next(v for v in s['vehicles'] if v['device_imei'] == 'A')
b = next(v for v in s['vehicles'] if v['device_imei'] == 'B')
eq('vehicle totals', (a['issues'], a['litres'], a['cost']), (2, 60.0, 300000))
eq('measured from full tanks only', (a['measured_km'], a['measured_litres']), (320.0, 40.0))
eq('measured km per litre', a['km_per_l'], 8.0)
eq('excess litres beyond baseline (40 - 320/10)', a['excess_litres'], 8.0)
eq('excess cost at the average price', a['excess_cost'], 40000)
eq('cost per km', a['cost_per_km'], 625.0)
eq('open reviews and flagged', (a['open_reviews'], a['flagged']), (1, 1))
eq('no profile: no excess', (b['excess_litres'], b['km_per_l']), (None, None))
eq('driver totals', [(d['driver_uid'], d['issues'], d['cost']) for d in s['drivers']],
   [('d-2', 2, 256000), ('d-1', 1, 200000)])
eq('totals', s['totals'], {'issues': 3, 'litres': 90.0, 'cost': 456000,
                           'open_reviews': 1, 'excess_cost': 40000})
eq('empty period', fr.summarise([], {})['totals']['issues'], 0)

if __name__ == '__main__':
    failed = [r for r in RESULTS if not r[1]]
    for name, ok_, detail in RESULTS:
        print('%s  %s%s' % ('PASS' if ok_ else 'FAIL', name,
                            '' if ok_ else '  -- ' + detail))
    print('\n%d passed, %d failed' % (len(RESULTS) - len(failed), len(failed)))
    sys.exit(1 if failed else 0)
