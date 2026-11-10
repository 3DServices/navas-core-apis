"""tests/test_waswa_fleet.py — the fleet tools' rules, without a database.

Three things here are worth more than the rest of the module put together, and
none of them need Postgres, Cassandra or Google to check:

  * whose fleet a call may read,
  * how much a route probe is allowed to cost,
  * and whether a day of GPS fixes turns into the right trips.

waswa_fleet imports Flask, psycopg2 and requests, which a bare checkout may
not have, so the functions under test are compiled out of the source file
rather than imported. Run:  python tests/test_waswa_fleet.py   (or via pytest)
"""

from __future__ import annotations

import ast
import io
import math
import os
from datetime import datetime, timedelta

_SOURCE = os.path.join(os.path.dirname(__file__), '..', 'endpoints', 'waswa_fleet.py')

_WANT_FUNCS = (
    '_target_client', 'build_scope', '_metres', '_num', '_stamp',
    '_thin', '_segment', '_summarise', 'dispatch',
    '_as_date', '_days', '_clock', '_trip', '_real',
)
_WANT_CLASSES = ('FleetUnavailable',)
_WANT_CONSTS = (
    '_MAX_PROBES', '_PROBE_SPACING_M', '_TRIP_GAP_MINUTES', '_MOVING_SPEED',
    # _stamp reads these at call time, so they must come across with it.
    '_DATE_FORMATS', '_TIME_FORMATS', '_MAX_DAYS', '_PLACEHOLDERS',
)


def _load():
    tree = ast.parse(io.open(_SOURCE, encoding='utf-8').read())
    body = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in _WANT_FUNCS:
            body.append(node)
        elif isinstance(node, ast.ClassDef) and node.name in _WANT_CLASSES:
            body.append(node)
        elif isinstance(node, ast.Assign):
            names = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if any(n in _WANT_CONSTS for n in names):
                body.append(node)
    names = {n.name for n in body if isinstance(n, ast.FunctionDef)}
    missing = set(_WANT_FUNCS) - names
    assert not missing, f'waswa_fleet no longer defines {missing}'

    namespace = {'math': math, 'datetime': datetime, 'timedelta': timedelta, 're': __import__('re')}
    exec(compile(ast.Module(body=body, type_ignores=[]), _SOURCE, 'exec'), namespace)
    return namespace


NS = _load()
NS.setdefault('_warn', lambda *a, **k: None)
_target_client = NS['_target_client']
build_scope = NS['build_scope']
_metres = NS['_metres']
_thin = NS['_thin']
_segment = NS['_segment']
_summarise = NS['_summarise']
dispatch = NS['dispatch']
_real = NS['_real']
_trip = NS['_trip']
_clock = NS['_clock']
_days = NS['_days']
_as_date = NS['_as_date']
FleetUnavailable = NS['FleetUnavailable']
_stamp = NS['_stamp']

CUSTOMER = build_scope('USER-2', 'CLIENT-1', is_staff=False)
STAFF = build_scope('STAFF-7', 'THREED', is_staff=True)


# ── Whose fleet may this call read ──────────────────────────────────────────

def test_a_customer_reads_their_own_fleet():
    assert _target_client(CUSTOMER, None) == 'CLIENT-1'


def test_a_customer_naming_another_client_still_reads_their_own():
    # The whole point. A model that has been talked into passing someone
    # else's client_uid must not widen what the caller can see.
    assert _target_client(CUSTOMER, 'CLIENT-9') == 'CLIENT-1'


def test_staff_may_name_a_client():
    assert _target_client(STAFF, 'CLIENT-9') == 'CLIENT-9'


def test_staff_naming_nobody_falls_back_to_their_own_scope():
    assert _target_client(STAFF, None) == 'THREED'


def test_no_scope_at_all_reads_nothing():
    # Never "everything" — a missing scope is a refusal, not a wildcard.
    assert _target_client(None, 'CLIENT-9') is None
    assert _target_client({}, 'CLIENT-9') is None


# ── What the model is allowed to pass ───────────────────────────────────────

def _spy():
    """A dispatch table that records the arguments it was handed."""
    seen = {}

    def tool(**kwargs):
        seen.update(kwargs)
        return {'ok': True}

    NS['_DISPATCH'] = {'unit_find': tool}
    return seen


def test_a_customers_client_uid_argument_is_dropped():
    seen = _spy()
    dispatch('unit_find', {'query': 'UBK 415K', 'client_uid': 'CLIENT-9'},
             scope=CUSTOMER)
    assert 'client_uid' not in seen, 'a customer must not choose whose fleet to read'
    assert seen['query'] == 'UBK 415K'


def test_staffs_client_uid_argument_survives():
    seen = _spy()
    dispatch('unit_find', {'query': 'x', 'client_uid': 'CLIENT-9'}, scope=STAFF)
    assert seen['client_uid'] == 'CLIENT-9'


def test_a_scope_argument_from_the_model_is_always_dropped():
    seen = _spy()
    dispatch('unit_find',
             {'query': 'x', 'scope': {'is_staff': True, 'client_uid': 'CLIENT-9'}},
             scope=CUSTOMER)
    assert seen['scope'] == CUSTOMER, 'the served scope must win'


def test_an_unknown_tool_is_passed_on_rather_than_swallowed():
    NS['_DISPATCH'] = {}
    assert dispatch('knowledge_search', {}, scope=CUSTOMER) is None


def test_bad_arguments_come_back_readable_instead_of_raising():
    def tool(**kwargs):
        raise TypeError('unexpected keyword argument')
    NS['_DISPATCH'] = {'unit_find': tool}
    out = dispatch('unit_find', {'nonsense': 1}, scope=CUSTOMER)
    assert 'error' in out


# ── What a probe is allowed to cost ─────────────────────────────────────────

def _point(lat, lon, speed=60, at=None):
    return {'lat': lat, 'lon': lon, 'speed': speed,
            'at': at or datetime(2026, 9, 29, 8, 0, 0), 'place': ''}


def test_probes_are_never_closer_together_than_the_spacing():
    spacing = NS['_PROBE_SPACING_M']
    # ~11m apart: a dense urban track. Naively probing each would be 200 calls.
    dense = [_point(0.3476 + i * 0.0001, 32.5825) for i in range(200)]
    kept = _thin(dense)
    for a, b in zip(kept, kept[1:]):
        assert _metres(a['lat'], a['lon'], b['lat'], b['lon']) >= spacing - 1


def test_the_probe_count_is_capped():
    cap = NS['_MAX_PROBES']
    sprawling = [_point(0.3476 + i * 0.01, 32.5825) for i in range(500)]
    assert len(_thin(sprawling)) <= cap


def test_thinning_a_dense_track_cuts_it_by_orders_of_magnitude():
    dense = [_point(0.3476 + i * 0.0001, 32.5825) for i in range(2000)]
    kept = _thin(dense)
    assert len(kept) <= NS['_MAX_PROBES']
    assert len(kept) < len(dense) / 50, 'the whole point is to not bill 2000 calls'


def test_a_single_point_still_gets_probed_once():
    assert len(_thin([_point(0.3476, 32.5825)])) == 1


def test_no_points_means_no_calls():
    assert _thin([]) == []


# ── Turning fixes into trips ────────────────────────────────────────────────

def _track(start, count, minutes_apart=1, lat0=0.3476):
    return [_point(lat0 + i * 0.001, 32.5825, speed=50,
                   at=start + timedelta(minutes=i * minutes_apart))
            for i in range(count)]


def test_a_gap_in_reporting_ends_a_trip():
    gap = NS['_TRIP_GAP_MINUTES']
    morning = _track(datetime(2026, 9, 29, 8, 0), 10)
    afternoon = _track(datetime(2026, 9, 29, 8, 0) + timedelta(minutes=10 + gap + 30),
                       10, lat0=0.40)
    assert len(_segment(morning + afternoon)) == 2


def test_continuous_reporting_is_one_trip():
    assert len(_segment(_track(datetime(2026, 9, 29, 8, 0), 30))) == 1


def test_a_lone_fix_is_not_a_trip():
    # One point is a position, not a journey; reporting it as a trip of 0 km
    # would put a meaningless row in front of the customer.
    assert _segment([_point(0.3476, 32.5825)]) == []


def test_a_summary_measures_distance_and_speed():
    start = datetime(2026, 9, 29, 8, 0)
    trip = [
        _point(0.3476, 32.5825, speed=0, at=start),
        _point(0.3576, 32.5825, speed=80, at=start + timedelta(minutes=10)),
        _point(0.3676, 32.5825, speed=40, at=start + timedelta(minutes=20)),
    ]
    out = _summarise(trip)
    assert out['max_speed_kph'] == 80
    assert out['duration_minutes'] == 20
    assert out['fixes'] == 3
    # 0.02 degrees of latitude is about 2.2 km.
    assert 2.0 < out['distance_km'] < 2.5


def test_a_stationary_fix_does_not_drag_the_moving_average_down():
    start = datetime(2026, 9, 29, 8, 0)
    trip = [
        _point(0.3476, 32.5825, speed=0, at=start),
        _point(0.3486, 32.5825, speed=60, at=start + timedelta(minutes=1)),
        _point(0.3496, 32.5825, speed=60, at=start + timedelta(minutes=2)),
    ]
    assert _summarise(trip)['average_moving_speed_kph'] == 60


def test_distance_is_measured_not_guessed():
    # Kampala to Entebbe is roughly 35 km as the crow flies.
    km = _metres(0.3476, 32.5825, 0.0512, 32.4637) / 1000
    assert 30 < km < 40


# ── Reading the clocks the devices actually write ───────────────────────────

def test_a_twelve_hour_heartbeat_keeps_its_time():
    # The exact shape dll_pulse_status_registry was observed holding. Getting
    # this wrong does not error — it silently returns midnight, and Waswa then
    # calls a unit that reported seconds ago "8 hours silent".
    got = _stamp('02-10-2026', '08:25:50AM')
    assert got == datetime(2026, 10, 2, 8, 25, 50), got


def test_pm_is_not_read_as_am():
    assert _stamp('02-10-2026', '08:25:50PM') == datetime(2026, 10, 2, 20, 25, 50)


def test_noon_and_midnight_do_not_swap():
    assert _stamp('02-10-2026', '12:00:00AM') == datetime(2026, 10, 2, 0, 0, 0)
    assert _stamp('02-10-2026', '12:00:00PM') == datetime(2026, 10, 2, 12, 0, 0)


def test_a_twenty_four_hour_clock_still_works():
    assert _stamp('02-10-2026', '14:30:00') == datetime(2026, 10, 2, 14, 30, 0)


def test_the_location_table_date_order_is_day_first():
    # 10-03-2026 is 10 March, not 3 October. Reading it the other way would
    # move a unit's last fix by seven months.
    assert _stamp('10-03-2026', '11:49:10AM') == datetime(2026, 3, 10, 11, 49, 10)


def test_an_unreadable_time_keeps_the_date_rather_than_losing_both():
    assert _stamp('02-10-2026', 'nonsense') == datetime(2026, 10, 2, 0, 0, 0)


def test_an_unreadable_date_is_unknown_not_epoch():
    # None means "we do not know". A zero date would become a unit that last
    # reported in 1970 and a trip 56 years long.
    assert _stamp('nonsense', '08:25:50AM') is None
    assert _stamp(None, '08:25:50AM') is None


# ── An outage is not an empty fleet ─────────────────────────────────────────

def test_an_unreachable_register_is_not_reported_as_no_vehicles():
    def tool(**kwargs):
        raise FleetUnavailable('OperationTimedOut')
    NS['_DISPATCH'] = {'unit_find': tool}

    out = dispatch('unit_find', {'query': 'UBK 415K'}, scope=CUSTOMER)
    assert out['unavailable'] is True
    assert out['found'] is False
    # The whole point: nothing in the reason may read as "you own nothing".
    lowered = out['reason'].lower()
    for forbidden in ('no units are registered', 'no vehicles on this account',
                      '0 units', 'zero units'):
        assert forbidden not in lowered, forbidden
    assert 'could not be reached' in lowered


def test_an_outage_is_distinguishable_from_a_genuinely_empty_account():
    def empty(**kwargs):
        return {'found': False, 'reason': 'no units are registered to this account'}
    NS['_DISPATCH'] = {'unit_find': empty}
    out = dispatch('unit_find', {}, scope=CUSTOMER)
    assert not out.get('unavailable'), 'an empty account is not an outage'


def test_an_ordinary_failure_is_still_an_error_not_an_outage():
    def broken(**kwargs):
        raise ValueError('something else entirely')
    NS['_DISPATCH'] = {'unit_find': broken}
    out = dispatch('unit_find', {}, scope=CUSTOMER)
    assert 'error' in out
    assert not out.get('unavailable')


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
         f0=None, f1=None, driver=None,
         loc0='Kabale Road, Kishwahili', loc1='Namilyango, Mukono'):
    return ('350317173603857', 'trip-1', __import__('datetime').date(2026, 10, 2),
            '08:56:16AM', t1, m0, m1, f0, f1, driver, loc0, loc1, status)


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


if __name__ == '__main__':
    passed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith('test_') and callable(fn):
            fn()
            passed += 1
            print('  ok  ' + name)
    print(f'{passed}/{passed} passed')
