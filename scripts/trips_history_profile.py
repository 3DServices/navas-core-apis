#!/usr/bin/env python3
"""
trips_history_profile.py -- where do the ~12 seconds of a trips/history
request actually go?

B8 was measured at 11% of the request (scripts/b8_audit.py). An audit of the
route found no per-fix external call: Config_Sources is cached per request
since B5, io_events_store is called once, and location_store.fixes() is one
read. So the remaining ~12s has no obvious owner, and guessing at it has
already been wrong twice in this codebase. This measures it.

Every significant function the route calls is wrapped with a timer. The
wrappers are nesting-aware: find_trips() calls Calculate_DistanceX(), so a
naive total would count the same seconds twice. Each entry reports

  total  -- wall time including anything it called
  self   -- total minus the time spent inside other TRACKED functions

and only `self` is summed, so the percentages add up. Whatever is left is
reported as UNACCOUNTED, which is the honest name for "in the route's own
code, or in something this script does not wrap".

Read-only. It issues ordinary requests and restores every patch afterwards.

Usage:
    python scripts/trips_history_profile.py
    python scripts/trips_history_profile.py --record-count 50
    python scripts/trips_history_profile.py --repeat 3
"""

import argparse
import sys
import threading
import time as _time
from collections import OrderedDict

sys.path.insert(0, '.')

ROUTE = '/data-stream/trips/history'

STATS = OrderedDict()           # label -> {'calls', 'total', 'self'}
_stack = threading.local()


def _push():
    if not hasattr(_stack, 'frames'):
        _stack.frames = []
    _stack.frames.append(0.0)       # time this frame's children consumed


def _pop(elapsed):
    child = _stack.frames.pop()
    if _stack.frames:
        _stack.frames[-1] += elapsed
    return elapsed - child


def track(label, func):
    def wrapper(*a, **kw):
        _push()
        began = _time.time()
        try:
            return func(*a, **kw)
        finally:
            elapsed = _time.time() - began
            own = _pop(elapsed)
            row = STATS.setdefault(label, {'calls': 0, 'total': 0.0,
                                           'self': 0.0, 'each': []})
            row['calls'] += 1
            row['total'] += elapsed
            row['self'] += own
            row['each'].append(own)
    wrapper.__name__ = getattr(func, '__name__', label)
    return wrapper


def patch_all():
    """Wrap everything the route calls. Returns a list of undo callables."""
    from endpoints import data as D
    undo = []

    def wrap(owner, name, label):
        original = getattr(owner, name, None)
        if original is None or not callable(original):
            return
        setattr(owner, name, track(label, original))
        undo.append(lambda: setattr(owner, name, original))

    # the route's own helpers
    for name in ('check_device', 'CheckHardware2', 'find_trips',
                 'Calculate_DistanceX', 'Config_Sources',
                 'get_cassandra_session'):
        wrap(D, name, name)

    # the stores
    wrap(D.location_store, 'fixes', 'location_store.fixes')
    wrap(D.location_store, 'as_history_tuple', 'location_store.as_history_tuple')
    for name in ('events_for', 'names_for', 'vendor_io_id'):
        wrap(D.io_events_store, name, 'io_events_store.' + name)

    # Postgres connect, which the route still does at the top
    wrap(D.psycopg2, 'connect', 'psycopg2.connect')

    return undo


def run(client, imei, start, end, count):
    payload = {'data': {'device_imei': imei, 'from_date': start,
                        'to_date': end, 'offset_log': '0',
                        'record_count': str(count)}}
    began = _time.time()
    res = client.post(ROUTE, json=payload)
    body = res.get_json() or {}
    return (res.status_code, str(body.get('message', '')), body.get('data'),
            _time.time() - began)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--imei', default='862846042622426')
    ap.add_argument('--day', default='25-09-2026')
    ap.add_argument('--record-count', type=int, default=10)
    ap.add_argument('--rtt-ms', type=float, default=0,
                    help='measured round-trip time (scripts/pg_connect_cost.py '
                         'prints it as "SELECT 1 on an open conn"). With it, '
                         'the report converts seconds into round trips.')
    ap.add_argument('--repeat', type=int, default=1,
                    help='run N times; the FIRST is reported separately '
                         'because caches and the Cassandra warm-up only pay '
                         'once')
    args = ap.parse_args()

    from app import app
    client = app.test_client()
    undo = patch_all()

    try:
        print('unit %s, day %s, record_count %d'
              % (args.imei, args.day, args.record_count))

        for attempt in range(1, args.repeat + 1):
            STATS.clear()
            _stack.frames = []
            code, message, data, wall = run(client, args.imei, args.day,
                                            args.day, args.record_count)
            raw = (data or {}).get('raw_data') or []
            trips = (data or {}).get('trips_data') or []

            print('')
            print('=' * 72)
            print('  run %d of %d   HTTP %s %r   %d fixes, %d trips   %.2fs'
                  % (attempt, args.repeat, code, message[:26],
                     len(raw), len(trips), wall))
            print('=' * 72)

            if code != 200:
                print('   not a 200 -- nothing to apportion')
                continue

            rows = sorted(STATS.items(), key=lambda kv: -kv[1]['self'])
            tracked = sum(r['self'] for _, r in rows)

            print('   %-34s %6s %9s %9s %7s'
                  % ('stage', 'calls', 'total', 'self', '% req'))
            for label, r in rows:
                if r['self'] < 0.005 and r['total'] < 0.005:
                    continue
                print('   %-34s %6d %8.2fs %8.2fs %6.1f%%'
                      % (label, r['calls'], r['total'], r['self'],
                         100.0 * r['self'] / wall if wall else 0))
                # An AVERAGE hides the shape. Config_Sources averaged 29ms
                # across 40 calls, which reads like CPU -- but if it is really
                # 4 cache misses at one network round trip each and 36 free
                # hits, that is latency and it vanishes in production. Only
                # the spread can tell those apart.
                if r['calls'] > 1:
                    each = sorted(r['each'])
                    slow = sum(1 for t in each if t > 0.100)
                    print('   %-34s        min %.0fms  med %.0fms  max %.0fms'
                          '   %d call(s) over 100ms'
                          % ('', each[0] * 1000, each[len(each) // 2] * 1000,
                             each[-1] * 1000, slow))

            unaccounted = wall - tracked
            print('   %-34s %6s %9s %8.2fs %6.1f%%'
                  % ('UNACCOUNTED (route\'s own code)', '', '',
                     unaccounted, 100.0 * unaccounted / wall if wall else 0))
            print('   %-34s %6s %9s %8.2fs' % ('request total', '', '', wall))

            if rows:
                worst, wr = rows[0]
                print('')
                if wr['self'] > 0.5 * wall:
                    print('   >> %s is over half the request. That is the' % worst)
                    print('      ticket, whatever the queue says.')
                elif unaccounted > 0.5 * wall:
                    print('   >> over half the time is in the route\'s own code,')
                    print('      not in anything it calls. Look at the loop that')
                    print('      builds raw_data, not at the stores.')
                else:
                    print('   >> no single stage dominates. The cost is spread;')
                    print('      the top entries are where to look first.')

        if args.rtt_ms:
            print('')
            print('   At %d ms per round trip, this request is about %.0f'
                  % (args.rtt_ms, wall / (args.rtt_ms / 1000.0)))
            print('   network round trips. On a co-located server those cost')
            print('   milliseconds, so these seconds do NOT transfer to')
            print('   production -- only the round-trip COUNT does.')

        if args.repeat > 1:
            print('')
            print('   Run 1 pays the Cassandra handshake and fills the')
            print('   per-request caches. Later runs are the steady state.')
    finally:
        for restore in undo:
            restore()
    return 0


if __name__ == '__main__':
    sys.exit(main())
