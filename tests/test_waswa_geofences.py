#!/usr/bin/env python3
"""
test_waswa_geofences.py -- how Waswa's geofences_list describes a zone's shape.

The app shows "Circle · 13000 m radius"; Waswa should say the same thing in
words. describe_zone_shape is compiled out of waswa_fleet.py (importing the
module needs the database). Which vehicles are inside is tested with
fleet_summary.units_by_zone in test_fleet_summary.py.
"""

import ast
import io
import os

_SOURCE = os.path.join(os.path.dirname(__file__), '..', 'endpoints',
                       'waswa_fleet.py')


def _load():
    tree = ast.parse(io.open(_SOURCE, encoding='utf-8').read())
    body = [n for n in tree.body
            if isinstance(n, ast.FunctionDef) and n.name == 'describe_zone_shape']
    assert body, 'waswa_fleet.py no longer defines describe_zone_shape'
    ns = {}
    exec(compile(ast.Module(body=body, type_ignores=[]), _SOURCE, 'exec'), ns)
    return ns['describe_zone_shape']


describe = _load()


def test_a_circle_gives_its_radius_in_km_or_m():
    assert describe('circle', {'center': {'lat': 0.3, 'lng': 32.5},
                               'radius_m': 13000}) == {'shape': 'circle',
                                                       'radius': '13 km'}
    assert describe('circle', {'radius_m': 250})['radius'] == '250 m'


def test_a_line_is_a_route_with_its_width():
    out = describe('line', {'points': [{}, {}, {}], 'width_m': 50})
    assert out == {'shape': 'line (a route)', 'route_points': 3,
                   'width': '50 m'}


def test_a_polygon_counts_its_corners_and_old_zones_still_read():
    assert describe('polygon', {'points': [{}] * 5}) == {'shape': 'polygon',
                                                         'corners': 5}
    # Zones from before migration 043 have no shape or params at all.
    assert describe(None, None) == {'shape': 'polygon'}
    assert describe('circle', None) == {'shape': 'circle'}


if __name__ == '__main__':
    passed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith('test_') and callable(fn):
            fn()
            passed += 1
            print('  ok  ' + name)
    print(f'{passed}/{passed} passed')
