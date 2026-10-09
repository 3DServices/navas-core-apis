#!/usr/bin/env python3
"""
b5_measure.py — the before and after for B5, in one tool.

Run it once before changing anything and it records a baseline: the exact
response JSON, how many queries the request issued, and which tables they hit.
Run it again after a change and it compares against that baseline and reports
whether the response is IDENTICAL.

That comparison is the pass/fail for every B5 stage. Wall time on this link
varies by seconds between identical runs — the earlier early-stop check timed
a 92-day window FASTER than a 1-day one purely from connection warm-up — so
timing alone cannot tell an optimisation from noise. Query counts can.

Counting without instrumenting production code
----------------------------------------------
get_cassandra_session() is a module-level function in endpoints.data, and
Config_Sources resolves it from module globals at call time. So replacing it
with a counting proxy here counts every Cassandra query the route makes,
without a line of measurement code shipping in data.py. The Postgres side is
counted by wrapping the connection the route opens.

The date is deliberately in the past. A live unit gains fixes while you watch,
and then "the response changed" would mean new telemetry rather than a
regression.

Usage:
    python scripts/b5_measure.py                      # capture or compare
    python scripts/b5_measure.py --reset               # discard the baseline
    python scripts/b5_measure.py --imei X --day Y --count N
"""

import argparse
import io
import json
import os
import sys
import time
from collections import Counter

sys.path.insert(0, '.')

CAPTURE = '.b5_capture.json'


class CountingSession(object):
    """Delegates to the real Cassandra session, counting by table."""

    def __init__(self, inner, tally):
        self._inner = inner
        self._tally = tally

    def _note(self, statement):
        text = getattr(statement, 'query_string', None) or str(statement)
        low = text.lower()
        for table in ('dll_device_local_configs',
                      'dll_io_events_executed_logs',
                      'dll_location_registry_by_record_ts',
                      'dll_device_basic_data'):
            if table in low:
                self._tally[f'C* {table}'] += 1
                return
        self._tally['C* other'] += 1

    def execute(self, statement, *a, **kw):
        self._note(statement)
        return self._inner.execute(statement, *a, **kw)

    def execute_async(self, statement, *a, **kw):
        # execute_concurrent_with_args goes through here, not through
        # execute(). Without this the concurrent batch was invisible and the
        # first B5 measurement showed 40 queries with no sign of the one
        # batched read that had replaced ten sequential scans.
        self._note(statement)
        return self._inner.execute_async(statement, *a, **kw)

    def prepare(self, query, *a, **kw):
        return self._inner.prepare(query, *a, **kw)

    def __getattr__(self, name):
        return getattr(self._inner, name)


class CountingCursor(object):
    def __init__(self, inner, tally):
        self._inner = inner
        self._tally = tally

    def execute(self, sql, *a, **kw):
        low = str(sql).lower()
        for table in ('dll_io_events_executed_logs', 'dll_io_events_config',
                      'dll_teltonika_avl_list', 'dll_location_registry',
                      'dll_device_basic_data', 'dll_device_registrar'):
            if table in low:
                self._tally[f'PG {table}'] += 1
                break
        else:
            self._tally['PG other'] += 1
        return self._inner.execute(sql, *a, **kw)

    def __enter__(self):
        self._inner.__enter__()
        return self

    def __exit__(self, *exc):
        return self._inner.__exit__(*exc)

    def __getattr__(self, name):
        return getattr(self._inner, name)


class CountingConnection(object):
    def __init__(self, inner, tally):
        self._inner = inner
        self._tally = tally
        tally['PG connections'] += 1

    def cursor(self, *a, **kw):
        return CountingCursor(self._inner.cursor(*a, **kw), self._tally)

    def __enter__(self):
        self._inner.__enter__()
        return self

    def __exit__(self, *exc):
        return self._inner.__exit__(*exc)

    def __getattr__(self, name):
        return getattr(self._inner, name)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--imei', default='862846042622426')
    ap.add_argument('--day', default='25-09-2026',
                    help='a PAST day — a live unit gains fixes mid-comparison')
    ap.add_argument('--count', type=int, default=10)
    ap.add_argument('--reset', action='store_true',
                    help='delete the stored baseline and capture afresh')
    args = ap.parse_args()

    if args.reset and os.path.exists(CAPTURE):
        os.remove(CAPTURE)
        print(f'removed {CAPTURE}')

    tally = Counter()

    from endpoints import data as data_module
    import psycopg2

    real_session = data_module.get_cassandra_session
    holder = {}

    def counted_session():
        if 'proxy' not in holder:
            inner = real_session()
            holder['proxy'] = (CountingSession(inner, tally)
                               if inner is not None else None)
        return holder['proxy']

    real_connect = psycopg2.connect

    def counted_connect(*a, **kw):
        return CountingConnection(real_connect(*a, **kw), tally)

    data_module.get_cassandra_session = counted_session
    psycopg2.connect = counted_connect
    try:
        from app import app
        client = app.test_client()
        body = {'data': {'device_imei': args.imei, 'from_date': args.day,
                         'to_date': args.day, 'offset_log': '0',
                         'record_count': str(args.count)}}
        t0 = time.time()
        res = client.post('/data-stream/trips/history', json=body)
        took = time.time() - t0
        payload = res.get_json() or {}
    finally:
        data_module.get_cassandra_session = real_session
        psycopg2.connect = real_connect

    data = payload.get('data')
    raw = len(data.get('raw_data', [])) if isinstance(data, dict) else 0
    trips = len(data.get('trips_data', [])) if isinstance(data, dict) else 0
    total = sum(tally.values()) - tally.get('PG connections', 0)

    print(f'unit {args.imei}, day {args.day}, record_count {args.count}')
    print(f'HTTP {res.status_code}  {str(payload.get("message", ""))[:40]!r}')
    print(f'raw_data {raw}, trips_data {trips}, {took:.2f}s\n')

    print('=' * 62)
    print('QUERIES ISSUED')
    print('=' * 62)
    for key in sorted(tally):
        print(f'   {key:<42} {tally[key]:>6}')
    print(f'   {"TOTAL queries":<42} {total:>6}')
    if raw:
        print(f'   {"per fix":<42} {total / raw:>6.1f}')

    snapshot = {
        'imei': args.imei, 'day': args.day, 'count': args.count,
        'status': res.status_code, 'response': payload,
    }

    if not os.path.exists(CAPTURE):
        io.open(CAPTURE, 'w', encoding='utf-8').write(
            json.dumps(snapshot, sort_keys=True, indent=1, default=str))
        print('\n' + '=' * 62)
        print('BASELINE RECORDED')
        print('=' * 62)
        print(f'   written to {CAPTURE}')
        print(f'   {total} queries for {raw} fix(es). Change the code, then')
        print('   run this again — it will compare.')
        return 0

    before = json.loads(io.open(CAPTURE, encoding='utf-8').read())
    print('\n' + '=' * 62)
    print('COMPARED WITH THE BASELINE')
    print('=' * 62)
    if (before.get('imei'), before.get('day'), before.get('count')) != \
            (args.imei, args.day, args.count):
        print('   !! the baseline was captured for a DIFFERENT request:')
        print(f'      baseline: {before.get("imei")} {before.get("day")} '
              f'count={before.get("count")}')
        print(f'      this run: {args.imei} {args.day} count={args.count}')
        print('      Use --reset, or re-run with the baseline\'s arguments.')
        return 1

    a = json.dumps(before.get('response'), sort_keys=True, default=str)
    b = json.dumps(payload, sort_keys=True, default=str)
    if before.get('status') != res.status_code:
        print(f'   !! status changed: {before.get("status")} -> '
              f'{res.status_code}')
        return 1
    if a == b:
        print('   RESPONSE IDENTICAL to the baseline, byte for byte.')
        print(f'   Queries now {total}. The baseline capture does not store')
        print('   its own count, so compare against what that run printed.')
        return 0

    print('   !! THE RESPONSE CHANGED. This is a regression, not a speed-up.')
    import difflib
    for line in list(difflib.unified_diff(
            a[:200000].splitlines(), b[:200000].splitlines(),
            fromfile='baseline', tofile='now', lineterm='', n=1))[:40]:
        print('   ' + line)
    print('\n   Revert the change, or explain the difference before keeping it.')
    return 1


if __name__ == '__main__':
    sys.exit(main())
