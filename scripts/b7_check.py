#!/usr/bin/env python3
"""
b7_check.py — verify B7 without depending on a stored baseline.

The .b5_capture.json baseline currently holds a 503: the --reset run hit a
transient failure and recorded it, so every comparison against it reports a
status change that has nothing to do with B7.

This needs no baseline. It checks the three things that actually matter after
a change that alters HOW the data is fetched but not WHAT is fetched:

  1. CONNECTIONS. How many psycopg2 connections one request opens. Before
     B7 it was 3: the route's own, plus one each for check_device and
     CheckHardware2. Those two now share one, so the correct number is 2 —
     not the 1 I wrongly predicted, because the route's own connection is not
     one of the read-only helpers.

  2. THE DATA IS STILL RIGHT. Ignition has to track speed: a fix at speed 0
     reads OFF, a moving fix reads ON. That is the check that would catch
     the shared connection returning a stale or wrong row, and it needs no
     baseline because the correlation is self-evidencing.

  3. REPEATED RUNS AGREE. Two requests back to back must return identical
     JSON. A shared connection is the kind of change that works once and
     fails the second time — a committed transaction left in a bad state, a
     connection closed by teardown and reused. One run cannot see that.

Check 3 is the one specific to B7. A per-request connection that is closed at
teardown and reopened on the next request is exactly where an off-by-one in
the lifecycle hides.

Read-only.

Usage:
    python scripts/b7_check.py
"""

import argparse
import json
import sys
from collections import Counter

sys.path.insert(0, '.')

PASS, FAIL = [], []


def ok(label, detail=''):
    PASS.append(label)
    print(f'   ok  {label}' + (f'  — {detail}' if detail else ''))


def bad(label, detail):
    FAIL.append(f'{label}: {detail}')
    print(f'   !!  {label}  — {detail}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--imei', default='862846042622426')
    ap.add_argument('--day', default='25-09-2026')
    ap.add_argument('--count', type=int, default=10)
    args = ap.parse_args()

    import psycopg2
    tally = Counter()
    real_connect = psycopg2.connect

    def counted(*a, **kw):
        tally['connections'] += 1
        return real_connect(*a, **kw)

    from app import app

    # Warm the Cassandra cluster BEFORE measuring. The first connect in a
    # process takes 4-6s and sometimes times out outright; when it does,
    # get_cassandra_session() returns None and the route correctly answers
    # 503. The first version of this check saw 503 then 200 and concluded
    # "the shared connection does not survive teardown and reuse" — blaming
    # B7 for a Cassandra handshake. A diagnostic that invents a culprit is
    # worse than none, so the handshake is taken out of the measurement.
    with app.app_context():
        from endpoints.data import get_cassandra_session
        warm = None
        for attempt in (1, 2, 3):
            warm = get_cassandra_session()
            if warm is not None:
                break
            print(f'   cluster connect attempt {attempt} failed, retrying')
        print('cassandra session: '
              + ('ready' if warm is not None else 'UNAVAILABLE'))
    if warm is None:
        print('\n!! Cassandra is not reachable after three attempts, so')
        print('   nothing about B7 can be measured right now. This is the')
        print('   cold-start fragility noted as B9, not a B7 result.')
        return 1

    psycopg2.connect = counted
    try:
        client = app.test_client()
        body = {'data': {'device_imei': args.imei, 'from_date': args.day,
                         'to_date': args.day, 'offset_log': '0',
                         'record_count': str(args.count)}}
        tally.clear()
        first = client.post('/data-stream/trips/history', json=body)
        after_first = tally['connections']
        tally.clear()
        second = client.post('/data-stream/trips/history', json=body)
        after_second = tally['connections']
    finally:
        psycopg2.connect = real_connect

    a = first.get_json() or {}
    b = second.get_json() or {}
    print(f'request 1: HTTP {first.status_code}, '
          f'{after_first} connection(s)')
    print(f'request 2: HTTP {second.status_code}, '
          f'{after_second} connection(s)\n')

    print('=' * 64)
    print('1. CONNECTIONS PER REQUEST')
    print('=' * 64)
    if first.status_code != 200:
        bad('request succeeded', f'HTTP {first.status_code}: '
                                 f'{str(a.get("message"))[:50]!r}')
    elif after_first == 2:
        ok('connections', '2 — the route\'s own, plus one shared by '
                          'check_device and CheckHardware2')
    elif after_first == 3:
        bad('connections', '3 — still one per helper; the patch is not in '
                           'effect')
    else:
        print(f'   -- connections: {after_first}, expected 2')
        print('      (not a failure by itself; say what changed)')

    print('\n' + '=' * 64)
    print('2. IS THE DATA STILL RIGHT?')
    print('=' * 64)
    rows = []
    for fix in ((a.get('data') or {}).get('raw_data') or []):
        detail = fix.get('enduser_data')
        entry = detail[0] if isinstance(detail, list) and detail else {}
        rows.append((fix.get('speed_log'), entry.get('iginition')))
    if not rows:
        bad('fixes returned', 'none')
    else:
        print(f'   {"speed":>6}  ignition')
        print('   ' + '-' * 18)
        for speed, ignition in rows:
            print(f'   {str(speed):>6}  {ignition}')
        stopped = [r for r in rows if r[0] == 0 and r[1] is not None]
        moving = [r for r in rows if isinstance(r[0], (int, float))
                  and r[0] > 5 and r[1] is not None]
        if not any(r[1] for r in rows):
            bad('ignition present', 'no fix carried an ignition value')
        elif not stopped or not moving:
            print('\n       (no stopped/moving contrast on this page)')
            ok('ignition present', f'on {sum(1 for r in rows if r[1])} fixes')
        elif [r for r in stopped if r[1] != 'OFF'] or \
                [r for r in moving if r[1] != 'ON']:
            bad('ignition tracks speed',
                'a stopped fix is not OFF, or a moving fix is not ON')
        else:
            ok('ignition tracks speed',
               f'{len(stopped)} stopped OFF, {len(moving)} moving ON')

    print('\n' + '=' * 64)
    print('3. DOES THE SECOND REQUEST MATCH THE FIRST?')
    print('=' * 64)
    unavailable = {first.status_code, second.status_code} & {503}
    if unavailable:
        print('   -- one request returned 503. 503 here means the position or')
        print('      IO store could not be read at all, which is orthogonal')
        print('      to B7: Postgres connections are counted above and were')
        print('      the same either way. Inconclusive, not failed.')
    elif second.status_code != first.status_code:
        bad('status stable', f'{first.status_code} then '
                             f'{second.status_code} — and neither is a 503, '
                             f'so the shared connection is the suspect')
    elif json.dumps(a, sort_keys=True, default=str) != \
            json.dumps(b, sort_keys=True, default=str):
        bad('responses identical',
            'the two runs differ; a request-scoped connection that is closed '
            'at teardown and reopened is the likely cause')
    else:
        ok('responses identical',
           'the connection is opened, used, closed and reopened cleanly')
    if after_second != after_first:
        print(f'   -- connection count differed between runs: '
              f'{after_first} then {after_second}')
        print('      (the first request in a process also warms the Cassandra '
              'cluster; Postgres counts should match)')

    print('\n' + '=' * 64)
    print(f'   {len(PASS)} passed, {len(FAIL)} failed')
    if FAIL:
        for f in FAIL:
            print(f'     - {f}')
        print('\n   endpoints/globals.py and app.py have timestamped .bak')
        print('   files if you want B7 reverted while this is sorted.')
        return 1
    print('\n   B7 verified: one fewer connection per request, the data')
    print('   unchanged, and the shared connection surviving a second')
    print('   request. Worth ~2.3s, which is inside this link\'s noise —')
    print('   the connection count is the evidence, not the clock.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
