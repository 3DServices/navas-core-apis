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
)
_WANT_CONSTS = (
    '_MAX_PROBES', '_PROBE_SPACING_M', '_TRIP_GAP_MINUTES', '_MOVING_SPEED',
)


def _load():
    tree = ast.parse(io.open(_SOURCE, encoding='utf-8').read())
    body = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in _WANT_FUNCS:
            body.append(node)
        elif isinstance(node, ast.Assign):
            names = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if any(n in _WANT_CONSTS for n in names):
                body.append(node)
    names = {n.name for n in body if isinstance(n, ast.FunctionDef)}
    missing = set(_WANT_FUNCS) - names
    assert not missing, f'waswa_fleet no longer defines {missing}'

    namespace = {'math': math, 'datetime': datetime, 're': __import__('re')}
    exec(compile(ast.Module(body=body, type_ignores=[]), _SOURCE, 'exec'), namespace)
    return namespace


NS = _load()
_target_client = NS['_target_client']
build_scope = NS['build_scope']
_metres = NS['_metres']
_thin = NS['_thin']
_segment = NS['_segment']
_summarise = NS['_summarise']
dispatch = NS['dispatch']

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


if __name__ == '__main__':
    passed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith('test_') and callable(fn):
            fn()
            passed += 1
            print('  ok  ' + name)
    print(f'{passed}/{passed} passed')
