#!/usr/bin/env python3
"""
b8_audit.py -- where does a trips/history request actually spend its time?

B8 was filed as "Calculate_DistanceX takes 2.2s per call". That is a cost per
call, not a cost per request, and the two are only the same if you know how
many calls a request makes. This measures it instead of assuming.

It wraps endpoints.data.Calculate_DistanceX with a counter that records every
call's arguments and wall time, then issues real requests and reports:

  - how many times the route calls it, against how many fixes and trips
  - how much of the request's wall time is inside it
  - how many calls are for a coordinate pair ALREADY requested in the same
    request -- the audit's main hypothesis

The hypothesis: find_trips() calls it for every speed>0 -> speed==0 segment
just to test the result against min_trip_distance = 1 km, throws the number
away, and then trips_history calls it AGAIN on the same two points to report
mileage. If that is right, every reported trip pays for the same road-distance
lookup twice, and the fix is a cache rather than anything clever.

Read-only: it issues ordinary GET/POST requests and patches nothing
persistently. It does make real distancematrix.ai calls, so it costs quota --
keep --record-count small.

Usage:
    python scripts/b8_audit.py
    python scripts/b8_audit.py --record-count 25 --day 25-09-2026
"""

import argparse
import json
import sys
import time as _time
from collections import Counter

sys.path.insert(0, '.')

ROUTE = '/data-stream/trips/history'

CALLS = []          # (args, seconds, returned_distance)


def install_probe():
    """Wrap Calculate_DistanceX in place. Returns the original."""
    from endpoints import data as data_module
    original = data_module.Calculate_DistanceX

    def probed(o_lat, o_lon, d_lat, d_lon):
        began = _time.time()
        out = original(o_lat, o_lon, d_lat, d_lon)
        took = _time.time() - began
        try:
            distance = json.loads(out).get('distance_covered')
        except Exception:                       # noqa: BLE001
            distance = '<unparseable>'
        CALLS.append(((str(o_lat), str(o_lon), str(d_lat), str(d_lon)),
                      took, distance))
        return out

    data_module.Calculate_DistanceX = probed
    return original


def call(client, imei, start, end, count):
    payload = {'data': {'device_imei': imei, 'from_date': start,
                        'to_date': end, 'offset_log': '0',
                        'record_count': str(count)}}
    began = _time.time()
    res = client.post(ROUTE, json=payload)
    body = res.get_json() or {}
    return (res.status_code, str(body.get('message', '')), body.get('data'),
            _time.time() - began)


def report(label, code, message, data, wall):
    raw = (data or {}).get('raw_data') or []
    trips = (data or {}).get('trips_data') or []

    spent = sum(c[1] for c in CALLS)
    pairs = Counter(c[0] for c in CALLS)
    repeats = sum(n - 1 for n in pairs.values() if n > 1)
    errors = sum(1 for c in CALLS if c[2] == 'CORDS_ERROR')

    print('')
    print('  %s' % label)
    print('   HTTP %s %r' % (code, message[:34]))
    print('   %-34s %d' % ('fixes returned (raw_data)', len(raw)))
    print('   %-34s %d' % ('trips returned (trips_data)', len(trips)))
    print('   %-34s %.2fs' % ('request wall time', wall))
    print('')
    print('   %-34s %d' % ('Calculate_DistanceX calls', len(CALLS)))
    print('   %-34s %.2fs  (%.0f%% of the request)'
          % ('time inside those calls', spent,
             (100.0 * spent / wall) if wall else 0))
    if CALLS:
        times = sorted(c[1] for c in CALLS)
        print('   %-34s %.2fs / %.2fs / %.2fs'
              % ('per call  min / median / max',
                 times[0], times[len(times) // 2], times[-1]))
    print('   %-34s %d distinct, %d repeated'
          % ('coordinate pairs', len(pairs), repeats))
    if errors:
        print('   %-34s %d' % ('calls that returned CORDS_ERROR', errors))

    if trips and len(CALLS) >= 2 * len(trips):
        print('')
        print('   >> %d calls for %d trips. find_trips() computes a distance'
              % (len(CALLS), len(trips)))
        print('      to test it against min_trip_distance and discards it;')
        print('      the caller then recomputes the SAME pair for mileage.')
    if repeats:
        worst = pairs.most_common(1)[0]
        print('')
        print('   >> %d call(s) asked for a pair already requested in this'
              % repeats)
        print('      same request. Worst pair was asked %d times.' % worst[1])
        print('      A per-request cache removes those with no API change.')
    if CALLS and spent / max(wall, 1e-9) > 0.5:
        print('')
        print('   >> over half the request is this one external API. B8 is')
        print('      the right ticket for this route.')
    elif CALLS:
        print('')
        print('   >> this API is NOT the dominant cost here. The rest of the')
        print('      time is elsewhere -- do not fix B8 expecting this route')
        print('      to get fast.')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--imei', default='862846042622426')
    ap.add_argument('--day', default='25-09-2026')
    ap.add_argument('--record-count', type=int, default=10)
    args = ap.parse_args()

    from app import app
    client = app.test_client()
    install_probe()

    print('unit %s, day %s, record_count %d'
          % (args.imei, args.day, args.record_count))
    print('(this makes real distancematrix.ai calls -- keep the count small)')

    code, message, data, wall = call(client, args.imei, args.day, args.day,
                                     args.record_count)
    report('trips/history, one day', code, message, data, wall)

    # --- the static findings, which need no network
    print('')
    print('  static findings (read from the source, not measured)')
    import io
    import re
    src = io.open('endpoints/data.py', 'r', newline='', encoding='utf-8').read()
    body = src[src.index('def Calculate_DistanceX'):]
    body = body[:body.index('\ndef ', 1)]

    # Look at the MODULE, not just this function's body. The first version
    # searched only inside Calculate_DistanceX and so reported "no connection
    # reuse" for code whose Session lives in the _distance_http() helper --
    # a false negative in the audit's own check.
    has_timeout = 'timeout' in body
    uses_session = 'requests.Session()' in src
    print('   %-34s %s' % ('requests.get has a timeout',
                           'yes' if has_timeout else
                           'NO -- a hung call blocks the worker for ever'))
    print('   %-34s %s' % ('reuses a connection (Session)',
                           'yes' if uses_session else
                           'no -- new TCP+TLS handshake per call'))
    print('   %-34s %s' % ('caches anything',
                           'yes, successes only'
                           if '_distance_cache_put' in src else 'no'))
    print('   %-34s %d (%d now conditional on a carried value)'
          % ('static call sites in data.py',
             src.count('Calculate_DistanceX(') - src.count('def Calculate_DistanceX('),
             src.count('trip.get("distance_km")')))
    return 0


if __name__ == '__main__':
    sys.exit(main())
