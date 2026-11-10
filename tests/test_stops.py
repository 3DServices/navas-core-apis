# -*- coding: utf-8 -*-
"""Tests for endpoints/stops.py  (B4)

stops.py is pure, so it imports directly -- no Flask, no Cassandra, no AST
extraction needed.

Run:  python tests/test_stops.py
"""

import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'endpoints'))

import stops                                              # noqa: E402

RESULTS = []


def check(name, ok, detail=''):
    RESULTS.append((name, bool(ok), detail))


def eq(name, got, want):
    check(name, got == want, 'got %r, want %r' % (got, want))


T0 = datetime(2026, 9, 25, 6, 0, 0)


def fix(offset_s, speed, lon=32.5800, lat=0.3100, place='Kampala', at_utc=True):
    """One fix. offset_s is seconds after T0."""
    return {
        'lon': lon, 'lat': lat, 'speed': speed, 'place': place,
        'at_utc': (T0 + timedelta(seconds=offset_s)) if at_utc else None,
        'at': T0 + timedelta(seconds=offset_s, hours=3),
    }


# ───────────────────────────────── 1. the basic shape

# parked for 30 minutes, one fix a minute
parked = [fix(i * 60, 0) for i in range(31)]
out = stops.detect(parked)
eq('one stop found', len(out['stops']), 1)
eq('dwell is 30 minutes', out['stops'][0]['dwell_seconds'], 1800)
eq('dwell reads well', out['stops'][0]['dwell'], '30m 0s')
eq('arrival is the FIRST fix', out['stops'][0]['arrival'], T0.isoformat())
eq('departure is the LAST fix', out['stops'][0]['departure'],
   (T0 + timedelta(minutes=30)).isoformat())
eq('fix_count recorded', out['stops'][0]['fix_count'], 31)
eq('place carried through', out['stops'][0]['place'], 'Kampala')

# this is the question trips/history could not answer
check('dwell time is answerable', out['stops'][0]['dwell_seconds'] == 1800)


# ───────────────────────────────── 2. moving fixes end a run

# 10 min parked, then driving, then 10 min parked somewhere else
mixed = ([fix(i * 60, 0) for i in range(11)]
         + [fix(660 + i * 60, 45, lon=32.60 + i * 0.01) for i in range(5)]
         + [fix(1000 + i * 60, 1, lon=32.70, lat=0.40) for i in range(11)])
out = stops.detect(mixed)
eq('two separate stops', len(out['stops']), 2)
eq('first stop dwell', out['stops'][0]['dwell_seconds'], 600)
eq('second stop dwell', out['stops'][1]['dwell_seconds'], 600)
check('stops are oldest first',
      out['stops'][0]['arrival'] < out['stops'][1]['arrival'])
eq('second stop is at the second place', out['stops'][1]['lon'], 32.70)

# jitter at 1 km/h still counts as stopped
eq('1 km/h is stationary', len(stops.detect([fix(i * 60, 1)
                                             for i in range(11)])['stops']), 1)
eq('2 km/h is stationary (the threshold)',
   len(stops.detect([fix(i * 60, 2) for i in range(11)])['stops']), 1)
eq('3 km/h is moving',
   len(stops.detect([fix(i * 60, 3) for i in range(11)])['stops']), 0)


# ───────────────────────────────── 3. min_dwell drops noise

eq('a 2-minute pause is not a stop',
   len(stops.detect([fix(i * 30, 0) for i in range(5)])['stops']), 0)
eq('exactly 3 minutes is a stop',
   len(stops.detect([fix(i * 60, 0) for i in range(4)])['stops']), 1)
eq('a single stationary fix is never a stop',
   len(stops.detect([fix(0, 0)])['stops']), 0)
eq('min_dwell is configurable',
   len(stops.detect([fix(i * 30, 0) for i in range(5)],
                    min_dwell_seconds=60)['stops']), 1)


# ───────────────────────────────── 4. the gap split
# Without this, an overnight silence reads as one continuous stop.

overnight = ([fix(0, 0), fix(60, 0), fix(120, 0), fix(180, 0)]          # 06:00-06:03
             + [fix(50000, 0), fix(50060, 0), fix(50120, 0), fix(50180, 0)])
out = stops.detect(overnight)
eq('a long silence splits the run', len(out['stops']), 2)
eq('first stop is only its own 3 minutes', out['stops'][0]['dwell_seconds'], 180)
eq('second stop is only its own 3 minutes', out['stops'][1]['dwell_seconds'], 180)
check('neither stop claims the whole gap',
      all(s['dwell_seconds'] < 1000 for s in out['stops']))

# inside the gap tolerance, the run stays whole
within = [fix(0, 0), fix(600, 0), fix(1200, 0)]   # 10-minute spacing, under 15
eq('10-minute spacing does not split', len(stops.detect(within)['stops']), 1)
eq('and keeps the full 20 minutes',
   stops.detect(within)['stops'][0]['dwell_seconds'], 1200)
eq('max_gap is configurable',
   len(stops.detect(within, max_gap_seconds=300)['stops']), 0)


# ───────────────────────────────── 5. a missing speed is NOT a stop

no_speed = [dict(fix(i * 60, 0), speed=None) for i in range(11)]
eq('None speed yields no stop', len(stops.detect(no_speed)['stops']), 0)
eq('empty-string speed yields no stop',
   len(stops.detect([dict(fix(i * 60, 0), speed='') for i in range(11)])['stops']), 0)
eq('garbage speed yields no stop',
   len(stops.detect([dict(fix(i * 60, 0), speed='NoData')
                     for i in range(11)])['stops']), 0)
eq('numeric string speed works',
   len(stops.detect([dict(fix(i * 60, 0), speed='0') for i in range(11)])['stops']), 1)
eq('speed with whitespace works',
   len(stops.detect([dict(fix(i * 60, 0), speed=' 0 ')
                     for i in range(11)])['stops']), 1)


# ───────────────────────────────── 6. the time basis
# A fix without record_timestamp is skipped, never guessed at via the EAT text.

half = [fix(i * 60, 0, at_utc=(i % 2 == 0)) for i in range(21)]
out = stops.detect(half)
eq('unplaceable fixes are counted', out['skipped_no_timestamp'], 10)
eq('and excluded from fix_count', out['fix_count'], 11)
check('the stop uses only placeable fixes', out['stops'][0]['fix_count'] == 11)

none_placeable = [fix(i * 60, 0, at_utc=False) for i in range(11)]
out = stops.detect(none_placeable)
eq('no placeable fixes -> no stops', len(out['stops']), 0)
eq('no placeable fixes -> all skipped', out['skipped_no_timestamp'], 11)

eq('empty input is handled', stops.detect([])['stops'], [])
eq('empty input reports zero fixes', stops.detect([])['fix_count'], 0)

# detect() must not trust the caller's ordering -- fixes() returns newest first
backwards = list(reversed([fix(i * 60, 0) for i in range(31)]))
out = stops.detect(backwards)
eq('newest-first input still gives one stop', len(out['stops']), 1)
eq('newest-first input still gives 30 minutes',
   out['stops'][0]['dwell_seconds'], 1800)
eq('arrival is still the earliest', out['stops'][0]['arrival'], T0.isoformat())


# ───────────────────────── 7. the plausibility guard (device 862846042643919)

# 1,018 km of coordinates in a day, with speed_log never exceeding 11.
# 11 km/h x 24 h = 264 km, so the speed field cannot be describing this.
far = []
for i in range(25):
    far.append(fix(i * 3600, 11 if i % 2 else 3, lon=32.58 + i * 0.37))
plausible, detail = stops.speed_is_plausible(far)
check('implausible speeds are caught', plausible is False, str(detail))
check('the verdict shows its arithmetic',
      'travelled_km' in detail and 'reachable_km_at_max_speed' in detail,
      str(detail))
check('travelled far exceeds reachable',
      detail['travelled_km'] > detail['reachable_km_at_max_speed'], str(detail))
eq('max speed reported is surfaced', detail['max_speed_reported'], 11.0)

out = stops.detect(far)
eq('detect() flags it too', out['speed_trustworthy'], False)

# a vehicle that genuinely sat still is plausible: no distance to explain
plausible, detail = stops.speed_is_plausible(parked)
check('a stationary day is plausible', plausible is True, str(detail))
eq('detect() trusts it', stops.detect(parked)['speed_trustworthy'], True)

# an ordinary drive is plausible: 60 km/h for an hour, 50 km covered
drive = [fix(i * 60, 60, lon=32.58 + i * 0.0075) for i in range(61)]
plausible, detail = stops.speed_is_plausible(drive)
check('an ordinary drive is plausible', plausible is True, str(detail))

check('too few fixes is not called implausible',
      stops.speed_is_plausible([fix(0, 0)])[0] is True)


# ───────────────────────────────── 8. drift and geometry

# a stationary unit whose coordinates wander slightly
wobble = [fix(i * 60, 0, lon=32.5800 + (i % 3) * 0.0001) for i in range(11)]
out = stops.detect(wobble)
eq('wobble is still one stop', len(out['stops']), 1)
check('drift is measured and small',
      0 < out['stops'][0]['drift_m'] < 50, str(out['stops'][0]['drift_m']))

eq('zero distance is zero', stops.haversine_km(32.58, 0.31, 32.58, 0.31), 0.0)
check('one degree of latitude is about 111 km',
      110 < stops.haversine_km(32.58, 0.0, 32.58, 1.0) < 112,
      str(stops.haversine_km(32.58, 0.0, 32.58, 1.0)))

eq('human_duration: seconds', stops.human_duration(45), '45s')
eq('human_duration: minutes', stops.human_duration(125), '2m 5s')
eq('human_duration: hours', stops.human_duration(7265), '2h 1m')
eq('human_duration: zero', stops.human_duration(0), '0s')
eq('human_duration: negative clamps', stops.human_duration(-5), '0s')


# ───────────────────────────────── 9. settings are reported back

out = stops.detect(parked, stationary_speed=5, min_dwell_seconds=60,
                   max_gap_seconds=300)
eq('settings echoed: speed', out['settings']['stationary_speed'], 5)
eq('settings echoed: dwell', out['settings']['min_dwell_seconds'], 60)
eq('settings echoed: gap', out['settings']['max_gap_seconds'], 300)


# ───────── 10. the integrated bound, and why max_speed alone was not enough
#
# b4_route_check.py on the live route exposed this.  Device 862846042643919 on
# 25-09-2026: 783 km covered, max speed_log 38, so max_speed x elapsed allowed
# 911 km and the day passed as plausible.  But 783 km at a 38 km/h ceiling
# needs 20.6 HOURS of unbroken driving at full speed, on a day that also held
# 25 stops.  The max-speed bound is so loose it passes almost anything; the
# integral of speed over time is the real test.

def dense(n, speed_at, km_total, minutes=1):
    """n fixes, `minutes` apart, advancing km_total in total."""
    deg = (km_total / 111.32) / max(1, n - 1)
    return [fix(i * 60 * minutes, speed_at(i), lon=32.58 + i * deg)
            for i in range(n)]


# the real shape: dense fixes, half of them parked, 783 km covered
real_shape = dense(1440, lambda i: 0 if i % 2 else 38, 783.0)
plausible, detail = stops.speed_is_plausible(real_shape)
eq('dense data uses the integral', detail['basis'], 'integrated')
check('the real-world shape IS caught by the integral', plausible is False,
      str(detail))
check('integrated is far below travelled',
      detail['integrated_km'] < detail['travelled_km'], str(detail))
check('max_speed alone would have passed it',
      detail['travelled_km'] < detail['reachable_km_at_max_speed'],
      'this is exactly the loophole: %s < %s'
      % (detail['travelled_km'], detail['reachable_km_at_max_speed']))

# a consistent dense day passes
honest = dense(1440, lambda i: 40, 900.0)
plausible, detail = stops.speed_is_plausible(honest)
check('a consistent dense day is plausible', plausible is True, str(detail))
eq('and on the integral', detail['basis'], 'integrated')

# ── the false positive the density gate prevents
#
# With fixes an hour apart, a trapezoid between two parked endpoints
# integrates to nearly nothing even if the vehicle drove hard in between.
# Integrating that would call an ordinary long-haul day impossible.

sparse = [fix(i * 3600, 0 if i % 2 else 60, lon=32.58 + i * 0.45)
          for i in range(25)]
plausible, detail = stops.speed_is_plausible(sparse)
check('sparse data does NOT use the integral',
      detail['basis'].startswith('max_speed'), str(detail))
check('and is not falsely flagged', plausible is True, str(detail))
check('though the integral would have flagged it',
      detail['travelled_km'] > detail['integrated_km'] * 1.25,
      'integral %s vs travelled %s -- a false alarm avoided'
      % (detail['integrated_km'], detail['travelled_km']))

eq('median gap is reported', detail['median_gap_seconds'], 3600.0)

# ── missing speeds drop coverage below the threshold -> fallback
patchy = [fix(i * 60, None if i % 3 else 40, lon=32.58 + i * 0.004)
          for i in range(100)]
plausible, detail = stops.speed_is_plausible(patchy)
check('low speed coverage falls back to max_speed',
      detail['basis'].startswith('max_speed'), str(detail))
check('coverage is reported and low', detail['speed_coverage'] < 0.8,
      str(detail))

# ── a stationary day has no distance to explain
plausible, detail = stops.speed_is_plausible(parked)
eq('no distance -> its own basis', detail['basis'], 'no distance to explain')
check('and is plausible', plausible is True, str(detail))

# ── the verdict must always agree with its own stated arithmetic
for name, rows in (('real_shape', real_shape), ('honest', honest),
                   ('sparse', sparse), ('patchy', patchy), ('far', far),
                   ('drive', drive)):
    verdict, d = stops.speed_is_plausible(rows)
    if 'allowed_km' in d:
        consistent = (verdict is True) == (d['travelled_km'] <= d['allowed_km'])
        check('verdict matches arithmetic: %s' % name, consistent, str(d))

check('every detail names its basis',
      all('basis' in stops.speed_is_plausible(r)[1]
          for r in (real_shape, honest, sparse, patchy, far, drive, parked)))

# a device reporting fixes but NO usable speed is its own basis, not 'none'.
# A caller classifying these would otherwise file it under "too few fixes"
# and lose the finding.
no_speed_at_all = [dict(fix(i * 60, 0, lon=32.58 + i * 0.004), speed=None)
                   for i in range(100)]
plausible, detail = stops.speed_is_plausible(no_speed_at_all)
eq('no usable speed has its own basis', detail['basis'], 'no speed data')
check('and is not called plausible', plausible is False, str(detail))
eq("'none' is reserved for too-few-fixes",
   stops.speed_is_plausible([fix(0, 0)])[1]['basis'], 'none')
check("too-few-fixes stays plausible",
      stops.speed_is_plausible([fix(0, 0)])[0] is True)


# ───────────────────────────────── report

FAILED = [r for r in RESULTS if not r[1]]
for name, ok, detail in RESULTS:
    if not ok:
        print('FAIL  %s  -- %s' % (name, detail))

print('')
print('%d/%d passed' % (len(RESULTS) - len(FAILED), len(RESULTS)))
sys.exit(1 if FAILED else 0)
