# -*- coding: utf-8 -*-
"""Tests for endpoints/token_usage.py

token_usage.py is pure, so it imports directly -- no Flask, no database.

Run:  python tests/test_token_usage.py
"""

import os
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'endpoints'))

import token_usage as tu                                  # noqa: E402

RESULTS = []
TODAY = date(2026, 10, 12)


def eq(name, got, want):
    RESULTS.append((name, got == want, 'got %r, want %r' % (got, want)))


def snap(account, day, used, service='Live Tracking', unit='hour'):
    return {'account': account, 'service': service, 'unit': unit,
            'day': date(2026, 10, day), 'used': used}


# ── readings ──────────────────────────────────────────────────────────────
eq('units columns first', tu.reading({'token_used_units': '12.5', 'token_units_left': '87.5',
                                      'token_hours_used': '3'}), (12.5, 87.5))
eq('hours when units await first use',
   tu.reading({'token_used_units': 'units_unfined_waiting_for_first_use',
               'token_hours_used': '40', 'token_hours_left': '60'}), (40.0, 60.0))
eq('left unreadable is None', tu.reading({'token_used_units': '5',
                                          'token_units_left': 'oops'}), (5.0, None))
eq('nothing readable', tu.reading({'token_used_units': None,
                                   'token_hours_used': 'column deprecated'}), (None, None))

# ── daily ─────────────────────────────────────────────────────────────────
result = tu.daily([
    snap('a', 9, 100), snap('a', 10, 110), snap('a', 11, 124), snap('a', 12, 130),
    snap('b', 10, 5, 'Fuel Monitoring', 'event'), snap('b', 11, 9, 'Fuel Monitoring', 'event'),
    snap('b', 12, 2, 'Fuel Monitoring', 'event'),         # reset: unknown
    snap('c', 12, 50),                                      # first reading: unknown
], TODAY, 3)
eq('three days, oldest first', [d['day'] for d in result['days']],
   [date(2026, 10, 10), date(2026, 10, 11), date(2026, 10, 12)])
eq('day 10', result['days'][0]['by_service'], {'Live Tracking': 10.0})
eq('day 10 unknown: b had no reading on the 9th', result['days'][0]['unknown'], 1)
eq('day 11', result['days'][1]['by_service'],
   {'Live Tracking': 14.0, 'Fuel Monitoring': 4.0})
eq('day 12: reset and first reading are unknown, not 0',
   (result['days'][2]['by_service'], result['days'][2]['unknown']),
   ({'Live Tracking': 6.0}, 2))
eq('services, biggest first', result['services'], [
    {'service': 'Live Tracking', 'unit': 'hour', 'total': 30.0,
     'average_per_day': 10.0, 'known_days': 3},
    {'service': 'Fuel Monitoring', 'unit': 'event', 'total': 4.0,
     'average_per_day': 4.0, 'known_days': 1}])
eq('units never mixed', result['units'], {'hour': 30.0, 'event': 4.0})
eq('first reading', result['first_reading'], date(2026, 10, 9))

gap = tu.daily([snap('a', 10, 100), snap('a', 12, 120)], TODAY, 2)
eq('a missed reading leaves the next day unknown',
   [(d['by_service'], d['unknown']) for d in gap['days']], [({}, 0), ({}, 1)])

eq('two accounts of one service add up',
   tu.daily([snap('a', 11, 1), snap('a', 12, 3), snap('d', 11, 10), snap('d', 12, 15)],
            TODAY, 1)['days'][0]['by_service'], {'Live Tracking': 7.0})

empty = tu.daily([], TODAY, 7)
eq('no history', (len(empty['days']), empty['services'], empty['first_reading']),
   (7, [], None))
eq('days are capped', len(tu.daily([], TODAY, 1000)['days']), tu.MAX_DAYS)


if __name__ == '__main__':
    failed = [r for r in RESULTS if not r[1]]
    for name, ok, detail in RESULTS:
        print('%s  %s%s' % ('PASS' if ok else 'FAIL', name,
                            '' if ok else '  -- ' + detail))
    print('\n%d passed, %d failed' % (len(RESULTS) - len(failed), len(failed)))
    sys.exit(1 if failed else 0)
