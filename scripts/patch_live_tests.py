#!/usr/bin/env python3
"""Tests for the two traps in the live-data rewrite.

Both of these produce wrong answers rather than errors, which is the only kind
worth writing a test for here:

  * a date range over a TEXT DD-MM-YYYY partition key, which sorts
    '01-09-2026' before '31-08-2026' and would silently return the wrong days;
  * end_time holding 'Incoming' while a trip is still running, which would be
    reported to a customer as the time their trip ended.

Neither needs a database.

Idempotent.
"""
import ast
import io
import sys

PATH = 'tests/test_waswa_fleet.py'

BLOCK = '''

# ── Walking a day-partitioned, text-dated store ─────────────────────────────

def test_a_range_is_expanded_into_one_entry_per_day():
    days = _days('28-09-2026', '02-10-2026')
    assert days == ['28-09-2026', '29-09-2026', '30-09-2026',
                    '01-10-2026', '02-10-2026'], days


def test_the_days_are_chronological_even_though_the_text_is_not():
    # The whole reason this helper exists. As strings these sort
    # '01-10-2026' < '28-09-2026' < '30-09-2026', so anything that trusted
    # lexicographic order over this column would hand back the wrong days and
    # report no error at all.
    days = _days('28-09-2026', '02-10-2026')
    assert days != sorted(days), 'if these ever sort as text, the trap is gone'
    assert days[0] == '28-09-2026' and days[-1] == '02-10-2026'


def test_one_day_is_one_query():
    assert _days('02-10-2026', '02-10-2026') == ['02-10-2026']


def test_a_backwards_range_is_read_the_way_it_was_meant():
    assert _days('02-10-2026', '30-09-2026') == ['30-09-2026', '01-10-2026',
                                                 '02-10-2026']


def test_an_enormous_range_is_capped_rather_than_attempted():
    # Each day is a separate Cassandra round trip; "this year" must not become
    # 365 of them inside one chat turn.
    assert len(_days('01-01-2026', '31-12-2026')) == NS['_MAX_DAYS']


def test_an_unreadable_range_asks_for_nothing():
    assert _days(None, '02-10-2026') == []
    assert _days('rubbish', '02-10-2026') == []


# ── A trip that has not finished yet ────────────────────────────────────────

def _row(status='ended', t1='05:42:11PM', m0='1000', m1='1042.5',
         f0=None, f1=None, driver=None):
    return ('350317173603857', 'trip-1', __import__('datetime').date(2026, 10, 2),
            '08:56:16AM', t1, m0, m1, f0, f1, driver,
            'Kabale Road, Kishwahili', 'Namilyango, Mukono', status)


def test_a_finished_trip_reports_its_end_and_its_distance():
    trip = _trip(_row())
    assert trip['in_progress'] is False
    assert trip['ended'] == '05:42:11PM'
    assert trip['distance_km'] == 42.5
    assert trip['to'] == 'Namilyango, Mukono'


def test_a_running_trip_never_reports_incoming_as_a_time():
    # dll_trips_auditor writes 'Incoming' into end_time while a trip is open.
    # Handing that to a customer as the time their trip ended would be absurd,
    # and handing it to the model is how absurd answers get written.
    trip = _trip(_row(status='started', t1='Incoming'))
    assert trip['in_progress'] is True
    assert trip['ended'] is None
    assert trip['to'] is None, 'a trip still running has no destination yet'


def test_an_unmeasured_trip_has_no_distance_rather_than_zero():
    # A trip of unknown length is not a trip of no length. Zero would be added
    # into a fleet total and quietly understate it.
    assert _trip(_row(m0=None, m1=None))['distance_km'] is None
    assert _trip(_row(m0='1000', m1=None))['distance_km'] is None


def test_an_odometer_that_went_backwards_is_not_a_negative_journey():
    assert _trip(_row(m0='1042.5', m1='1000'))['distance_km'] is None


def test_fuel_is_reported_only_when_both_readings_are_there():
    assert 'fuel_used' not in _trip(_row(f0='80'))
    assert _trip(_row(f0='80', f1='62.5'))['fuel_used'] == 17.5


def test_a_driver_is_named_only_when_one_is_recorded():
    assert 'driver_id' not in _trip(_row())
    assert _trip(_row(driver='D-77'))['driver_id'] == 'D-77'
'''


def main():
    src = io.open(PATH, encoding='utf-8', newline='').read()
    if 'test_the_days_are_chronological' in src:
        print('  live-data tests already present')
        return 0

    # The harness compiles named functions out of the module; name the new ones.
    src = src.replace(
        "    '_thin', '_segment', '_summarise', 'dispatch',",
        "    '_thin', '_segment', '_summarise', 'dispatch',\n"
        "    '_as_date', '_days', '_clock', '_trip',", 1)
    if "'_as_date'" not in src:
        print('  !! could not extend _WANT_FUNCS — stopping')
        return 1

    src = src.replace("    '_DATE_FORMATS', '_TIME_FORMATS',",
                      "    '_DATE_FORMATS', '_TIME_FORMATS', '_MAX_DAYS',", 1)
    if "'_MAX_DAYS'" not in src:
        print('  !! could not extend _WANT_CONSTS — stopping')
        return 1

    # _days needs timedelta in the extracted namespace.
    src = src.replace(
        "    namespace = {'math': math, 'datetime': datetime,",
        "    namespace = {'math': math, 'datetime': datetime, 'timedelta': timedelta,", 1)

    for name in ('_as_date', '_days', '_clock', '_trip'):
        anchor = "dispatch = NS['dispatch']"
        src = src.replace(anchor, anchor + f"\n{name} = NS['{name}']", 1)

    marker = "if __name__ == '__main__':"
    at = src.find(marker)
    if at < 0:
        print('  !! runner block not found')
        return 1
    src = src[:at] + BLOCK.strip('\n') + '\n\n\n' + src[at:]

    ast.parse(src)
    io.open(PATH, 'w', encoding='utf-8', newline='').write(src)
    print('  added 12 tests for the date-range and open-trip traps')
    print(f'  written: {PATH}')
    print('  syntax OK')
    return 0


if __name__ == '__main__':
    sys.exit(main())
