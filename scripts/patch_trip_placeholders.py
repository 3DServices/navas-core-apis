#!/usr/bin/env python3
"""Three things the first live run exposed.

1. driver_id comes back as the literal string "NoData". Passed through, Waswa
   tells a customer their driver was NoData. The table uses placeholder strings
   where other tables would use NULL, so they have to be recognised.

2. fuel_used came back as 0.0 on every trip, because start_fuel_level and
   end_fuel_level are both 0 — there is no fuel sensor on these units. "Fuel
   used: 0.0" states a measurement that was never taken. A customer reading it
   would reasonably conclude the vehicle burned nothing. Absent and zero are
   different facts and must not render the same.

3. The two trip tools disagree about what "a week" means, and both were right
   about their own window:

       unit_trips     25-09 to 02-10   16 trips   29.75 km
       fleet_activity 26-09 to 02-10   10 trips   17.98 km

   Same vehicle, same run. unit_trips was given explicit dates spanning eight
   calendar days; fleet_activity(days=7) counts seven inclusive. Both return
   their from/to, so the figures are reconcilable — but only if the answer says
   which window it used. Quoting "10 trips last week" and "16 trips last week"
   in one conversation is the self-contradiction this whole rewrite exists to
   prevent, so the model is now told to state the range.

Idempotent.
"""
import ast
import io
import sys

FLEET = 'endpoints/waswa_fleet.py'
ASSIST = 'endpoints/assistant.py'
TESTS = 'tests/test_waswa_fleet.py'

REAL = '''
# dll_trips_auditor writes placeholder text where a NULL belongs — "NoData" in
# driver_id is the one that showed up first. Passing those through verbatim is
# how a customer gets told their driver was NoData, so they are read as absent.
_PLACEHOLDERS = frozenset((
    '', '-', '--', 'nodata', 'no data', 'none', 'null', 'nil',
    'n/a', 'na', 'unknown', 'undefined', 'not set', 'notset',
))


def _real(value):
    """The text, or None if it is a placeholder standing in for nothing."""
    text = str(value if value is not None else '').strip()
    return None if text.lower() in _PLACEHOLDERS else (text or None)

'''

OLD_TRIP_TAIL = '''    out = {
        'trip_uid': str(uid) if uid else None,
        'date': date.isoformat() if hasattr(date, 'isoformat') else str(date),
        'started': _clock(t0),
        'ended': _clock(t1) if ended else None,
        'in_progress': not ended,
        'distance_km': km,
        'from': str(loc0 or '').strip() or None,
        'to': (str(loc1 or '').strip() or None) if ended else None,
        'status': state or None,
    }
    fuel0, fuel1 = _num(f0), _num(f1)
    if fuel0 is not None and fuel1 is not None and fuel0 >= fuel1:
        out['fuel_used'] = round(fuel0 - fuel1, 2)
    if driver:
        out['driver_id'] = str(driver)
    return out'''

NEW_TRIP_TAIL = '''    out = {
        'trip_uid': str(uid) if uid else None,
        'date': date.isoformat() if hasattr(date, 'isoformat') else str(date),
        'started': _clock(t0),
        'ended': _clock(t1) if ended else None,
        'in_progress': not ended,
        'distance_km': km,
        'from': _real(loc0),
        'to': _real(loc1) if ended else None,
        'status': _real(state),
    }

    # Fuel only when something was actually measured. Both readings sitting at
    # zero means there is no fuel sensor, not that the trip burned nothing, and
    # "fuel_used: 0.0" is a claim about a measurement that never happened.
    fuel0, fuel1 = _num(f0), _num(f1)
    if (fuel0 is not None and fuel1 is not None
            and fuel0 >= fuel1 and (fuel0 or fuel1)):
        out['fuel_used'] = round(fuel0 - fuel1, 2)

    driver_id = _real(driver)
    if driver_id:
        out['driver_id'] = driver_id
    return out'''

PROMPT = '''        # unit_trips takes a date range; fleet_activity takes a number of
        # days. Asked about "last week" they can return different counts for
        # the same vehicle, both correct for their own window. Every tool result
        # carries from/to, so the only way to contradict yourself here is to
        # quote a figure without the window it came from.
        messages.append({"role": "system", "content": (
            "Trip counts, distances and fleet totals are always FOR A DATE "
            "RANGE, and every tool result carries the from/to it used. Say the "
            "range whenever you give such a figure — \\"16 trips between 25 Sep "
            "and 2 Oct\\", not \\"16 trips last week\\". If two results cover "
            "different ranges, do not reconcile them by picking one: say what "
            "each covers.")})

'''

TEST_BLOCK = '''

# ── Placeholders are not data ───────────────────────────────────────────────

def test_the_literal_string_nodata_is_not_a_driver():
    # The first live run returned driver_id 'NoData'. Passed through, Waswa
    # tells a customer their driver was NoData.
    assert 'driver_id' not in _trip(_row(driver='NoData'))
    assert 'driver_id' not in _trip(_row(driver='  none  '))
    assert 'driver_id' not in _trip(_row(driver='N/A'))
    assert _trip(_row(driver='D-77'))['driver_id'] == 'D-77'


def test_a_placeholder_location_is_absent_not_quoted():
    assert _trip(_row(loc0='NoData'))['from'] is None


def test_no_fuel_sensor_is_not_zero_fuel_used():
    # Both readings at zero means nothing was measured. Reporting 0.0 would
    # tell a customer the vehicle burned no fuel, which is a different claim.
    assert 'fuel_used' not in _trip(_row(f0='0', f1='0'))
    assert 'fuel_used' not in _trip(_row(f0=0, f1=0))


def test_real_fuel_figures_still_come_through():
    assert _trip(_row(f0='80', f1='62.5'))['fuel_used'] == 17.5
    # A full tank run down to empty is a real measurement, not a placeholder.
    assert _trip(_row(f0='40', f1='0'))['fuel_used'] == 40.0
'''


def patch_fleet():
    src = io.open(FLEET, encoding='utf-8', newline='').read()
    notes = []

    if '_PLACEHOLDERS' in src:
        notes.append('_real already present')
    else:
        at = src.find('def _trip_rows(')
        if at < 0:
            return None, ['!! _trip_rows not found']
        src = src[:at] + REAL.lstrip('\n') + '\n' + src[at:]
        notes.append('added _real() and the placeholder set')

    if "'from': _real(loc0)" in src:
        notes.append('_trip already filters placeholders')
    elif OLD_TRIP_TAIL in src:
        src = src.replace(OLD_TRIP_TAIL, NEW_TRIP_TAIL, 1)
        notes.append('_trip: placeholders dropped, fuel only when measured')
    else:
        return None, ['!! _trip tail not found verbatim']

    ast.parse(src)
    io.open(FLEET, 'w', encoding='utf-8', newline='').write(src)
    return src, notes


def patch_assistant():
    src = io.open(ASSIST, encoding='utf-8', newline='').read()
    if 'always FOR A DATE' in src:
        return 'date-range instruction already present'
    anchor = '        if module and surface in _SCREEN_SURFACES:'
    at = src.find(anchor)
    if at < 0:
        return '!! anchor not found'
    src = src[:at] + PROMPT + src[at:]
    ast.parse(src)
    io.open(ASSIST, 'w', encoding='utf-8', newline='').write(src)
    return 'added the date-range instruction'


def patch_tests():
    src = io.open(TESTS, encoding='utf-8', newline='').read()
    if 'test_the_literal_string_nodata_is_not_a_driver' in src:
        return 'placeholder tests already present'

    # The old fuel/driver tests are superseded by the ones below.
    for dead in ('def test_fuel_is_reported_only_when_both_readings_are_there():',
                 'def test_a_driver_is_named_only_when_one_is_recorded():'):
        at = src.find(dead)
        if at >= 0:
            end = src.find('\n\n\ndef ', at)
            if end < 0:
                end = src.find("\n\n\nif __name__", at)
            if end > at:
                src = src[:at] + src[end + 3:]

    marker = "if __name__ == '__main__':"
    at = src.find(marker)
    if at < 0:
        return '!! runner block not found'
    src = src[:at] + TEST_BLOCK.strip('\n') + '\n\n\n' + src[at:]
    ast.parse(src)
    io.open(TESTS, 'w', encoding='utf-8', newline='').write(src)
    return 'replaced 2 tests with 4 sharper ones'


def main():
    out, notes = patch_fleet()
    for n in notes:
        print('  ' + n)
    if out is None:
        return 1
    print('  ' + patch_assistant())
    print('  ' + patch_tests())
    print('  syntax OK')
    return 0


if __name__ == '__main__':
    sys.exit(main())
