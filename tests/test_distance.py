#!/usr/bin/env python3
"""
Unit tests for B8: Calculate_DistanceX and find_trips' carried distance.

endpoints/data.py imports Flask, psycopg2 and the Cassandra driver, so the
two functions are extracted by AST and run against a stubbed HTTP session --
the same pattern as test_reply_scrub.py and test_cassandra_store.py. No
network call is made by this suite.

The behaviour that matters:
  - a hung distancematrix.ai call must not hang the worker (timeout passed)
  - every failure path must still return JSON, because every caller does
    json.loads() on the result
  - a CORDS_ERROR must NOT be cached: one transient OVER_QUERY_LIMIT would
    otherwise be a permanent wrong answer for the life of the process
  - find_trips must hand its measured distance to the caller, so the same
    coordinate pair is not bought twice

Run as a plain script (pytest is not installed in the Windows venv):

    python tests/test_distance.py
"""

import ast
import io
import json
import logging
import os
import re
import sys
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
MODULE = os.path.join(HERE, '..', 'endpoints', 'data.py')

WANTED = ('Calculate_DistanceX', 'find_trips', '_distance_http',
          '_distance_cache_get', '_distance_cache_put')


class FakeResponse(object):
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class FakeSession(object):
    """Records every call; replays a queue of payloads or exceptions."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append({'url': url, 'params': params, 'timeout': timeout})
        reply = self.replies.pop(0) if self.replies else {}
        if isinstance(reply, Exception):
            raise reply
        return FakeResponse(reply)


def ok_payload(km='12.5 km', mins='20 mins'):
    return {'rows': [{'elements': [{'status': 'OK',
                                    'distance': {'text': km},
                                    'duration': {'text': mins}}]}]}


def status_payload(status):
    return {'rows': [{'elements': [{'status': status}]}]}


def load(session):
    src = io.open(MODULE, 'r', newline='', encoding='utf-8').read()
    tree = ast.parse(src.replace('\r\n', '\n'))
    kept = [n for n in tree.body
            if isinstance(n, ast.FunctionDef) and n.name in WANTED]
    missing = set(WANTED) - {n.name for n in kept}
    if missing:
        raise AssertionError('data.py is missing %s' % sorted(missing))

    ns = {
        'json': json, 're': re, 'os': os, 'logging': logging,
        'threading': threading,
        '_distance_local': threading.local(),
        'DISTANCE_TIMEOUT': (5, 15),
        '_DISTANCE_CACHE': {}, '_DISTANCE_CACHE_MAX': 4,
        '_distance_cache_lock': threading.Lock(),
        'requests': None,
    }
    exec(compile(ast.Module(body=kept, type_ignores=[]), MODULE, 'exec'), ns)
    # config is imported inside the function; stub the module it reads
    import types
    cfg = types.ModuleType('config')
    cfg.DISTANCEMATRIX_API_KEY = 'TEST-KEY'
    sys.modules['config'] = cfg
    ns['_distance_http'] = lambda: session
    return ns


PASSED, FAILED = [], []


def check(name, ok, detail=''):
    (PASSED if ok else FAILED).append(name)
    print('  %s %s%s' % ('ok ' if ok else '!! ', name,
                         '' if ok else '   <-- ' + detail))


def point(lat, lon, speed, stamp):
    return {'data_latitude': lat, 'data_longitude': lon,
            'speed_log': speed, 'local_system_timestamp': stamp}


def main():
    print('Calculate_DistanceX: the happy path')
    s = FakeSession([ok_payload()])
    ns = load(s)
    out = json.loads(ns['Calculate_DistanceX'](1, 2, 3, 4))
    check('returns the distance', out['distance_covered'] == '12.5')
    check('returns the duration', out['time_covered'] == '20')
    check('a timeout is passed to requests', s.calls[0]['timeout'] == (5, 15),
          'without it a hung call blocks the worker for ever')
    check('the key goes in params, not the URL',
          'key' in (s.calls[0]['params'] or {})
          and 'key=' not in s.calls[0]['url'])

    print('')
    print('Calculate_DistanceX: the cache')
    s = FakeSession([ok_payload(), ok_payload('99 km')])
    ns = load(s)
    first = ns['Calculate_DistanceX'](1, 2, 3, 4)
    second = ns['Calculate_DistanceX'](1, 2, 3, 4)
    check('a repeated pair is served from cache',
          first == second and len(s.calls) == 1, '%d calls' % len(s.calls))
    third = ns['Calculate_DistanceX'](9, 9, 9, 9)
    check('a different pair still calls out', len(s.calls) == 2)

    print('')
    print('Calculate_DistanceX: failures are JSON, and are not cached')
    for label, replies in (
            ('a timeout', [Exception('timed out'), ok_payload()]),
            ('ZERO_RESULTS', [status_payload('ZERO_RESULTS'), ok_payload()]),
            ('OVER_QUERY_LIMIT', [status_payload('OVER_QUERY_LIMIT'), ok_payload()]),
            ('REQUEST_DENIED', [status_payload('REQUEST_DENIED'), ok_payload()]),
            ('a malformed body', [{'rows': []}, ok_payload()])):
        s = FakeSession(replies)
        ns = load(s)
        raw = ns['Calculate_DistanceX'](1, 2, 3, 4)
        try:
            parsed = json.loads(raw)
            is_json = True
        except Exception:                       # noqa: BLE001
            parsed, is_json = None, False
        check('%s still returns JSON' % label, is_json,
              'every caller does json.loads() on this')
        check('%s reports CORDS_ERROR' % label,
              is_json and parsed['distance_covered'] == 'CORDS_ERROR')
        again = ns['Calculate_DistanceX'](1, 2, 3, 4)
        check('%s is NOT cached' % label,
              json.loads(again)['distance_covered'] == '12.5',
              'a transient failure would be permanent for this process')

    print('')
    print('Calculate_DistanceX: no API key')
    s = FakeSession([ok_payload()])
    ns = load(s)
    sys.modules['config'].DISTANCEMATRIX_API_KEY = ''
    out = json.loads(ns['Calculate_DistanceX'](1, 2, 3, 4))
    check('no key -> CORDS_ERROR without calling out',
          out['distance_covered'] == 'CORDS_ERROR' and not s.calls)
    sys.modules['config'].DISTANCEMATRIX_API_KEY = 'TEST-KEY'

    print('')
    print('find_trips: the distance it measured reaches the caller')
    s = FakeSession([ok_payload('12.5 km')])
    ns = load(s)
    trips = ns['find_trips']([
        point(0.1, 32.1, '10', '01:00:00'),
        point(0.2, 32.2, '20', '02:00:00'),
        point(0.3, 32.3, '0', '03:00:00'),
    ])
    check('a trip is found', len(trips) == 1, '%d trips' % len(trips))
    check('it carries distance_km',
          bool(trips) and trips[0].get('distance_km') == 12.5,
          'without this every caller buys the same pair twice')
    check('find_trips called the API once', len(s.calls) == 1)

    print('')
    print('find_trips: a sub-threshold segment is still dropped')
    s = FakeSession([ok_payload('0.4 km')])
    ns = load(s)
    trips = ns['find_trips']([
        point(0.1, 32.1, '10', '01:00:00'),
        point(0.1, 32.1, '0', '02:00:00'),
    ])
    check('under 1 km is not a trip', trips == [], '%r' % trips)

    print('')
    print('=' * 62)
    print('  %d/%d passed' % (len(PASSED), len(PASSED) + len(FAILED)))
    if FAILED:
        for name in FAILED:
            print('    FAILED: %s' % name)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
