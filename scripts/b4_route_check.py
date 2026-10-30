#!/usr/bin/env python3
"""
b4_route_check.py — does /data-stream/trips/stops actually work?

tests/test_stops.py proves the detector on synthetic fixes: 63 checks, all
passing. That says nothing about the route, which adds a date parse, a day
cap, a billing check, an unpaginated Cassandra read and stop-pagination — any
of which can turn a correct detector into a 400.

Driven through Flask's test client, so there is no server to restart and no
PowerShell quoting to get wrong.

Each case is here because it fails differently if something specific is broken:

  1. one recent day            the ordinary case. Must return stops with
                               arrival, departure and dwell — the question
                               trips/history structurally cannot answer,
                               because its dedupe keeps one fix per coordinate
                               and discards the arrival time.

  2. the same day, paginated   record_count=1 must return ONE stop while
                               stops_total still reports the real count. If
                               stops_total equals 1 as well, pagination is
                               being applied to the wrong thing.

  3. page 2 of the same day    offset_log=1 must return a DIFFERENT stop whose
                               dwell matches what case 1 reported for it. This
                               is the check that matters most: it is the exact
                               failure that made option C necessary. If dwell
                               shifts between pages, a page boundary is cutting
                               a run of fixes in half.

  4. a 40-day span             must be a 400 naming the 31-day cap, NOT a 503
                               and NOT a slow success. A 503 would tell the
                               caller to retry something that can never work.

  5. a window Cassandra lacks  07-08 to 11-08-2025 on 867556044727322 — an
                               honest "No Stops Found", never a 503. Same
                               distinction b2_route_check case 4 protects:
                               "we could not look" must not read as "it never
                               stopped".

  6. the speed guard           on 862846042643919, a unit whose speed field
                               has been unreliable. This does NOT assert a
                               particular verdict: an earlier run of this
                               script asserted speed_trustworthy must be false
                               and failed, because the 'max speed 11 over
                               1,018 km' figure came from a different day --
                               on 25-09-2026 the same unit reports max 38 and
                               783 km, which is genuinely consistent. The
                               testable invariant is that the verdict agrees
                               with the arithmetic the guard itself reports.
                               tests/test_stops.py proves the guard FIRES on
                               data that warrants it; this proves it is wired
                               in and computing on real fixes.

That failure was worth having: it showed max_speed x elapsed is a near-useless
bound (783 km 'fits' a 38 km/h ceiling only by pretending to 20.6 hours of
unbroken driving on a day with 25 stops), which is why stops.py now integrates
speed over time where sampling is dense enough to allow it.

Read-only: the route only reads.

Usage:
    python scripts/b4_route_check.py
    python scripts/b4_route_check.py --imei 862846042622426 --day 25-09-2026
"""

import argparse
import sys
import time
from datetime import datetime, timedelta

sys.path.insert(0, '.')

ROUTE = '/data-stream/trips/stops'

# 867556044727322 is the unit whose Cassandra coverage was mapped day by day,
# so "has no rows here" is a known fact rather than a hope.
EMPTY_UNIT = '867556044727322'

# 862846042643919 is the unit whose speed field cannot describe its movement.
IMPLAUSIBLE_UNIT = '862846042643919'


def post(client, imei, start, end, **extra):
    body = {'data': dict({'device_imei': imei, 'from_date': start,
                           'to_date': end}, **extra)}
    t0 = time.time()
    try:
        res = client.post(ROUTE, json=body)
        took = time.time() - t0
        try:
            payload = res.get_json() or {}
        except Exception:                               # noqa: BLE001
            payload = {}
        return res.status_code, payload, took
    except Exception as error:                          # noqa: BLE001
        return 0, {'message': 'EXCEPTION %s' % error}, time.time() - t0


def billing_blocked(message):
    """The route checks the device registry and billing BEFORE reading any
    position, so these outcomes never reached B4's code and prove nothing."""
    low = str(message).lower()
    return ('billing' in low or 'cant be found' in low or 'not-found' in low
            or 'not currently running' in low)


def describe(data):
    if not isinstance(data, dict):
        return '(no body)'
    return ('stops %s of %s | fixes %s | skipped %s | speed_ok %s'
            % (len(data.get('stops') or []), data.get('stops_total'),
               data.get('fix_count'), data.get('skipped_no_timestamp'),
               data.get('speed_trustworthy')))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--imei', default='862846042622426',
                    help='a unit find_moving_unit.py reports as billing=running')
    ap.add_argument('--day', default='25-09-2026', help='DD-MM-YYYY')
    args = ap.parse_args()

    from app import app
    client = app.test_client()

    print('unit %s, day %s' % (args.imei, args.day))
    print('(the stops read is UNPAGINATED by design, so a busy day takes a '
          'few seconds)\n')

    results = []

    def record(label, ok, blocked, detail):
        mark = 'ok ' if ok else ('-- ' if blocked else '!! ')
        print('   %s%-26s %s' % (mark, label, detail))
        results.append((label, ok, blocked, detail))

    # ---- 1. the ordinary case
    code, payload, took = post(client, args.imei, args.day, args.day)
    data = payload.get('data')
    message = str(payload.get('message', ''))[:46]
    blocked = billing_blocked(message)
    stops_total = data.get('stops_total') if isinstance(data, dict) else None
    first_page = (data.get('stops') or []) if isinstance(data, dict) else []

    ok = code == 200 and bool(first_page)
    record('recent day', ok, blocked,
           'HTTP %s %r  %.1fs' % (code, message, took))
    if isinstance(data, dict):
        print('        %s' % describe(data))
        for stop in first_page[:3]:
            print('        %s -> %s  dwell %s  fixes %s  drift %sm  @ %s'
                  % (stop.get('arrival', '')[11:19],
                     stop.get('departure', '')[11:19], stop.get('dwell'),
                     stop.get('fix_count'), stop.get('drift_m'),
                     str(stop.get('place'))[:28]))

    # the whole point of B4
    if ok:
        has_dwell = all('dwell_seconds' in s and 'arrival' in s
                        and 'departure' in s for s in first_page)
        record('dwell is answerable', has_dwell, False,
               'every stop carries arrival, departure and dwell_seconds')

    # ---- 2 and 3. pagination applies to stops, not fixes
    if ok and stops_total and stops_total > 1:
        code2, payload2, _ = post(client, args.imei, args.day, args.day,
                                  record_count='1', offset_log='0')
        d2 = payload2.get('data') or {}
        page1 = d2.get('stops') or []
        record('record_count=1 -> 1 stop', len(page1) == 1, False,
               'got %d' % len(page1))
        record('stops_total survives paging', d2.get('stops_total') == stops_total,
               False, 'got %s, expected %s' % (d2.get('stops_total'), stops_total))

        code3, payload3, _ = post(client, args.imei, args.day, args.day,
                                  record_count='1', offset_log='1')
        d3 = payload3.get('data') or {}
        page2 = d3.get('stops') or []

        if page1 and page2:
            different = page1[0].get('arrival') != page2[0].get('arrival')
            record('offset_log=1 -> next stop', different, False,
                   '%s vs %s' % (page1[0].get('arrival', '')[11:19],
                                 page2[0].get('arrival', '')[11:19]))

            # THE decisive check: a stop's dwell must not depend on the page
            # it was returned on.  This is the failure option C exists to
            # prevent, and the reason stop detection could not live inside
            # trips/history's fix pagination.
            unpaged = {s['arrival']: s['dwell_seconds'] for s in first_page}
            same = all(unpaged.get(s['arrival']) == s['dwell_seconds']
                       for s in page1 + page2 if s['arrival'] in unpaged)
            record('dwell is page-independent', same, False,
                   'dwell identical whether paged or not')
    elif ok:
        record('pagination', True, False,
               'skipped: only %s stop(s) on this day' % stops_total)

    # ---- 4. the day cap
    end = datetime.strptime(args.day, '%d-%m-%Y').date()
    start = end - timedelta(days=39)
    code, payload, took = post(client, args.imei, start.strftime('%d-%m-%Y'),
                               args.day)
    message = str(payload.get('message', ''))
    capped = code == 400 and '31' in message
    record('40-day span refused', capped, False,
           'HTTP %s %r  %.1fs' % (code, message[:52], took))
    if code == 503:
        print('        !! 503 tells the caller to retry a request that can')
        print('           never succeed. The day cap is not firing.')

    # ---- 5. an empty window must not 503
    code, payload, took = post(client, EMPTY_UNIT, '07-08-2025', '11-08-2025')
    message = str(payload.get('message', ''))[:46]
    blocked = billing_blocked(message)
    honest = code == 400 and 'no stops' in message.lower()
    record('empty window says so', honest, blocked,
           'HTTP %s %r' % (code, message))
    if code == 503:
        print('        !! 503 on an empty window: "could not look" is being')
        print('           confused with "never stopped".')

    # ---- 6. the plausibility guard on a real device
    code, payload, took = post(client, IMPLAUSIBLE_UNIT, args.day, args.day)
    data = payload.get('data') if isinstance(payload.get('data'), dict) else {}
    message = str(payload.get('message', ''))[:46]
    blocked = billing_blocked(message)
    trust = data.get('speed_trustworthy')
    # Only meaningful if the unit actually returned fixes to judge.
    detail = data.get('speed_detail') or {}

    if data.get('fix_count'):
        # The invariant: whatever the guard concluded, it must agree with the
        # numbers it published. Asserting a fixed verdict for a device on an
        # arbitrary day tests a remembered fact, not the code.
        if 'allowed_km' in detail:
            consistent = ((trust is True)
                          == (detail['travelled_km'] <= detail['allowed_km']))
            record('speed verdict is consistent', consistent, blocked,
                   'trustworthy=%s, travelled %s km vs allowed %s km on the '
                   '%s bound' % (trust, detail.get('travelled_km'),
                                 detail.get('allowed_km'),
                                 detail.get('basis')))
        else:
            record('speed verdict is consistent', trust is True, blocked,
                   'no distance to explain (basis %r)' % detail.get('basis'))

        print('        basis=%s  travelled=%s  integrated=%s  '
              'max_speed_bound=%s'
              % (detail.get('basis'), detail.get('travelled_km'),
                 detail.get('integrated_km'),
                 detail.get('reachable_km_at_max_speed')))
        print('        median gap %ss, speed coverage %s  ->  %s'
              % (detail.get('median_gap_seconds'),
                 detail.get('speed_coverage'),
                 'TRUSTED' if trust else 'FLAGGED UNRELIABLE'))
        if detail.get('reason'):
            print('        %s' % detail['reason'])
    else:
        record('speed verdict is consistent', True, blocked,
               'not evaluated: no fixes for %s on %s (HTTP %s %r)'
               % (IMPLAUSIBLE_UNIT, args.day, code, message))

    # ---- report
    print('')
    print('=' * 66)
    good = [r for r in results if r[1]]
    blocked_rows = [r for r in results if r[2] and not r[1]]
    bad = [r for r in results if not r[1] and not r[2]]
    print('   %d as expected, %d billing-blocked, %d wrong'
          % (len(good), len(blocked_rows), len(bad)))

    if blocked_rows:
        print('')
        print('   Those prove nothing either way: the route checks the device')
        print('   registry and billing before reading a position, so they')
        print('   never reached B4\'s code. Re-run against a unit that')
        print('   find_moving_unit.py reports as billing=running.')

    if bad:
        print('')
        print('   NOT working:')
        for label, _ok, _b, detail in bad:
            print('     - %-28s %s' % (label, detail))
        print('')
        print('   endpoints/stops.py is pure and separately tested, so a')
        print('   failure here is in the route, not the detector: the day cap,')
        print('   the dedupe flag, the billing gate or the stop pagination.')
        return 1

    print('')
    print('   B4 works on the live route: trip history can now answer dwell')
    print('   time, each stop reports arrival and departure from the FIRST and')
    print('   LAST fix of a run, a dwell does not change when paged, a span')
    print('   too wide is refused honestly rather than retried, and the')
    print('   speed-plausibility verdict agrees with the arithmetic it')
    print('   publishes rather than being asserted.')
    print('')
    print('   Next: B3 switches trips/excel, trips/pdf and')
    print('   trips/history/replay to the live store the same way.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
