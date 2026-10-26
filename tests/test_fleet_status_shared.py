# -*- coding: utf-8 -*-
"""The fleet status cases shared with the OLIWA app
(tests/fixtures/fleet_status_cases.json), run against fleet_summary.py.

The app runs the same file (oliwa-mobile/test/fleet_status_shared_test.dart),
so a rule changed on one side only fails here or there instead of reaching a
client's dashboard as two different counts.

Run:  python tests/test_fleet_status_shared.py
"""

import json
import os
import sys
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'endpoints'))

import fleet_summary as fs                                # noqa: E402

FIXTURE = os.path.join(HERE, 'fixtures', 'fleet_status_cases.json')
# The app's copy, when oliwa-mobile is checked out beside this repository.
APP_COPY = os.path.join(os.path.dirname(os.path.dirname(HERE)), 'oliwa-mobile',
                        'test', 'fixtures', 'fleet_status_cases.json')

RESULTS = []


def check(name, ok, detail=''):
    RESULTS.append((name, bool(ok), detail))


def eq(name, got, want):
    check(name, got == want, 'got %r, want %r' % (got, want))


def reading(unit, now):
    ago = unit.get('minutes_ago')
    return {'imei': unit['id'], 'name': unit['id'],
            'snapshot': unit.get('frame'),
            'seen': None if ago is None else now - timedelta(minutes=ago),
            'unread': bool(unit.get('unread')),
            'never': bool(unit.get('never'))}


with open(FIXTURE, encoding='utf-8') as f:
    data = json.load(f)
now = datetime.fromisoformat(data['now'])

for case in data['cases']:
    readings = [reading(u, now) for u in case['units']]
    for unit, r in zip(case['units'], readings):
        eq('%s / %s' % (case['name'], unit['id']),
           fs.classify(r, now), unit['expect'])
    got = fs.fleet_status(readings, now)
    for key, want in case['expect'].items():
        eq('%s / %s' % (case['name'], key), got[key], want)

if os.path.exists(APP_COPY):
    with open(FIXTURE, 'rb') as a, open(APP_COPY, 'rb') as b:
        check("the app's copy is identical (copy this file to oliwa-mobile/"
              "test/fixtures/ after changing it)", a.read() == b.read())
else:
    print('(oliwa-mobile not checked out beside this repository: '
          'copy comparison skipped)')


if __name__ == '__main__':
    failed = [r for r in RESULTS if not r[1]]
    for name, ok, detail in RESULTS:
        print('%s  %s%s' % ('PASS' if ok else 'FAIL', name,
                            '' if ok else '  -- ' + detail))
    print('\n%d passed, %d failed' % (len(RESULTS) - len(failed), len(failed)))
    sys.exit(1 if failed else 0)
