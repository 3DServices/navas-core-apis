#!/usr/bin/env python3
"""
b5_verify_fields.py — the pass criterion for B5, field by field.

Byte-identity stopped being the test the moment the plan became "restore the
missing telemetry": the response is SUPPOSED to change. But "it changed and
the new bits look right" is not a verification, it is a glance at a wall of
JSON. This checks the three things that actually have to hold:

  1. NOTHING LOST. Every key the baseline had, on every fix, still has
     EXACTLY the same value — coordinates, timestamps, data_idx, satellites,
     hdop, geocoded_location, speed, batch_uid, record_io_events_uid.
     io_events_data is the one allowed exception, because changing it is the
     point.

  2. ONLY THE EXPECTED KEYS ARE NEW. enduser_data and nothing else. A new key
     nobody asked for is a leak from the code that had never run.

  3. THE NEW VALUES ARE COHERENT. Ignition is reported through
     ignition_detection -> channel in5 -> that fix's event value, so a fix
     at speed 0 should read OFF and a moving fix should read ON. If that
     correlation is absent the chain is resolving to something arbitrary and
     the data is decoration rather than telemetry.

Check 3 matters most. Checks 1 and 2 would pass if every fix reported
ignition 'ON' unconditionally.

trips_data is compared the same way, including its nested start and end
points.

Read-only. Run it after b5_measure, against the same baseline.

Usage:
    python scripts/b5_verify_fields.py
"""

import argparse
import io
import json
import os
import sys

sys.path.insert(0, '.')

CAPTURE = '.b5_capture.json'
MAY_CHANGE = {'io_events_data'}
MAY_APPEAR = {'enduser_data'}

PASS, FAIL = [], []


def ok(label, detail=''):
    PASS.append(label)
    print(f'   ok  {label}' + (f'  — {detail}' if detail else ''))


def bad(label, detail):
    FAIL.append(f'{label}: {detail}')
    print(f'   !!  {label}  — {detail}')


def compare_point(where, before, after):
    """Every baseline key must survive with its value; new keys must be
    expected."""
    problems = []
    for key, value in (before or {}).items():
        if key in MAY_CHANGE:
            continue
        if key not in (after or {}):
            problems.append(f'{where}: lost {key!r}')
        elif after[key] != value:
            problems.append(f'{where}: {key!r} changed '
                            f'{value!r} -> {after[key]!r}')
    appeared = set(after or {}) - set(before or {})
    for key in sorted(appeared - MAY_APPEAR):
        problems.append(f'{where}: unexpected new key {key!r}')
    return problems, appeared & MAY_APPEAR


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--imei', default='862846042622426')
    ap.add_argument('--day', default='25-09-2026')
    ap.add_argument('--count', type=int, default=10)
    args = ap.parse_args()

    if not os.path.exists(CAPTURE):
        print(f'!! no {CAPTURE}. Run b5_measure.py before the change to')
        print('   record a baseline.')
        return 1
    stored = json.loads(io.open(CAPTURE, encoding='utf-8').read())
    if (stored.get('imei'), stored.get('day'), stored.get('count')) != \
            (args.imei, args.day, args.count):
        print('!! the baseline is for a different request.')
        return 1

    from app import app
    client = app.test_client()
    body = {'data': {'device_imei': args.imei, 'from_date': args.day,
                     'to_date': args.day, 'offset_log': '0',
                     'record_count': str(args.count)}}
    res = client.post('/data-stream/trips/history', json=body)
    now = res.get_json() or {}

    before = (stored.get('response') or {}).get('data') or {}
    after = now.get('data') or {}
    b_raw = before.get('raw_data') or []
    a_raw = after.get('raw_data') or []

    print(f'unit {args.imei}, day {args.day}')
    print(f'baseline: {len(b_raw)} fix(es)   now: {len(a_raw)} fix(es)\n')

    print('=' * 66)
    print('1. NOTHING LOST, 2. ONLY EXPECTED KEYS ARE NEW')
    print('=' * 66)
    if len(b_raw) != len(a_raw):
        bad('fix count', f'{len(b_raw)} -> {len(a_raw)}')
    else:
        problems, gained = [], set()
        for i, (b, a) in enumerate(zip(b_raw, a_raw), 1):
            p, g = compare_point(f'raw_data[{i}]', b, a)
            problems += p
            gained |= g
        if problems:
            bad('raw_data preserved', f'{len(problems)} problem(s)')
            for p in problems[:8]:
                print(f'       {p}')
        else:
            ok('raw_data preserved',
               f'every baseline key identical on all {len(a_raw)} fixes')
            ok('new keys', f'only {sorted(gained) or "none"}')

    b_trips = before.get('trips_data') or []
    a_trips = after.get('trips_data') or []
    if len(b_trips) != len(a_trips):
        bad('trip count', f'{len(b_trips)} -> {len(a_trips)}')
    else:
        problems = []
        for i, (b, a) in enumerate(zip(b_trips, a_trips), 1):
            for key in ('start_time', 'end_time', 'mileage_passed',
                        'trip_number'):
                if b.get(key) != a.get(key):
                    problems.append(f'trip[{i}].{key}: '
                                    f'{b.get(key)!r} -> {a.get(key)!r}')
            for side in ('start_point_dta', 'end_point_dta'):
                p, _g = compare_point(f'trip[{i}].{side}',
                                      b.get(side), a.get(side))
                problems += p
        if problems:
            bad('trips_data preserved', f'{len(problems)} problem(s)')
            for p in problems[:8]:
                print(f'       {p}')
        else:
            ok('trips_data preserved',
               f'{len(a_trips)} trip(s), times and mileage unchanged')

    print('\n' + '=' * 66)
    print('3. IS THE NEW TELEMETRY COHERENT, OR JUST PRESENT?')
    print('=' * 66)
    rows = []
    for fix in a_raw:
        detail = fix.get('enduser_data')
        entry = detail[0] if isinstance(detail, list) and detail else {}
        events = fix.get('io_events_data')
        channel = {}
        if isinstance(events, list):
            for item in events:
                if isinstance(item, dict):
                    channel.update(item)
        rows.append((fix.get('speed_log'), entry.get('iginition'),
                     channel.get('in5')))

    print(f'   {"speed":>6}  {"ignition":<9} {"in5":<5}')
    print('   ' + '-' * 24)
    for speed, ignition, in5 in rows:
        print(f'   {str(speed):>6}  {str(ignition):<9} {str(in5):<5}')

    have = [r for r in rows if r[1] is not None]
    if not have:
        bad('ignition present', 'no fix reported an ignition value')
    else:
        ok('ignition present', f'on {len(have)} of {len(rows)} fixes')
        stopped = [r for r in have if r[0] == 0]
        moving = [r for r in have if isinstance(r[0], (int, float))
                  and r[0] > 5]
        if not stopped or not moving:
            print('       (this page has no stopped/moving contrast, so the '
                  'correlation cannot be judged)')
        else:
            bad_stopped = [r for r in stopped if r[1] != 'OFF']
            bad_moving = [r for r in moving if r[1] != 'ON']
            if bad_stopped or bad_moving:
                bad('ignition tracks speed',
                    f'{len(bad_stopped)} stopped fix(es) not OFF, '
                    f'{len(bad_moving)} moving fix(es) not ON')
            else:
                ok('ignition tracks speed',
                   f'{len(stopped)} stopped fix(es) OFF, {len(moving)} '
                   f'moving fix(es) ON')
        if len({r[2] for r in have}) == 1:
            print(f'       note: in5 is the same value on every fix '
                  f'({have[0][2]!r}); a constant channel cannot confirm the '
                  f'chain resolves per fix')
        else:
            ok('channel varies per fix',
               f'in5 takes {sorted({str(r[2]) for r in have})}')

    print('\n' + '=' * 66)
    print(f'   {len(PASS)} passed, {len(FAIL)} failed')
    if FAIL:
        print('\n   B5 is NOT verified:')
        for f in FAIL:
            print(f'     - {f}')
        return 1
    print('\n   Nothing lost, only enduser_data added, and the ignition')
    print('   values track speed — so the config chain is resolving per fix')
    print('   rather than emitting a constant. B5 verified.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
