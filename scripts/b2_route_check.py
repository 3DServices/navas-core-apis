#!/usr/bin/env python3
"""
b2_route_check.py — does /data-stream/trips/history actually work now?

B2 switched that route from the dead Postgres copy to location_store. The
reader is proved and the patch compiles, but neither fact exercises the route:
the handler still does per-fix IO-event lookups, a billing check and a date
guard, any of which can turn a correct reader into a 400.

This drives the real view through Flask's test client, so there is no server to
restart and no PowerShell quoting to get wrong. Five cases, each chosen because
it would fail differently if something specific were broken:

  1. one recent day on a busy unit      the case that returned NOTHING before
                                        B2, because Postgres has no rows after
                                        06-08-2025
  2. a 92-day span on that unit         the early stop under the real route; if
                                        it is not engaging this is slow or dies
  3. a window Cassandra has             867556044727322, 12-08 to 20-08-2025
  4. a window Cassandra does NOT have   07-08 to 11-08-2025 — must be an honest
                                        "No Trips Found", NOT a 503
  5. the old B1 window                  15-07 to 01-08-2025: Postgres had 1,934
                                        rows, Cassandra has none. Must say no
                                        trips rather than invent any.

Case 4 matters as much as case 1. A 503 there would mean the unavailable path
fires when the store is merely empty — the same confusion FleetUnavailable
exists to prevent.

Read-only: the route only reads.

Usage:
    python scripts/b2_route_check.py
    python scripts/b2_route_check.py --count 50
"""

import argparse
import json
import sys
import time

sys.path.insert(0, '.')

# The two 2025 cases pin a unit deliberately: 867556044727322 is the one whose
# Cassandra coverage we mapped day by day, so "has rows" and "has none" are
# known facts rather than hopes.
FIXED = (
    ('window Cassandra has',    '867556044727322', '12-08-2025', '20-08-2025',
     'rows'),
    ('window Cassandra lacks',  '867556044727322', '07-08-2025', '11-08-2025',
     'no trips'),
    ('the old B1 window',       '867556044727322', '15-07-2025', '01-08-2025',
     'no trips'),
)


def cases(imei, day, span):
    """The recent-date cases use whichever unit the route will accept.

    find_moving_unit.py names one that both drives and reports
    billing=running; a unit missing from Postgres dll_device_basic_data is
    rejected three guards before B2's code runs and tests nothing.
    """
    from datetime import datetime, timedelta
    end = datetime.strptime(day, '%d-%m-%Y').date()
    start = end - timedelta(days=span - 1)
    return (
        ('recent day', imei, day, day, 'rows'),
        (f'{span}-day span', imei, start.strftime('%d-%m-%Y'), day, 'rows'),
    ) + FIXED


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--imei', default='862846042622426',
                    help='a unit find_moving_unit.py reports as '
                         'billing=running')
    ap.add_argument('--day', default='25-09-2026',
                    help="DD-MM-YYYY, that unit's busiest trip day")
    ap.add_argument('--span', type=int, default=92,
                    help='how many days the wide-window case covers')
    ap.add_argument('--count', type=int, default=10,
                    help='record_count. The route runs 2 Postgres queries and '
                         '4 Config_Sources calls PER FIX — about 4 seconds a '
                         'row against the remote host — so keep this small. '
                         'That cost is pre-existing (ticket B5), not B2.')
    args = ap.parse_args()

    from app import app
    client = app.test_client()

    print(f'unit {args.imei}, day {args.day}, record_count {args.count}')
    print(f'(about {args.count * 4}s per row-returning case — the route\'s '
          f'per-fix fan-out, not B2)\n')
    results = []
    for label, imei, start, end, expect in cases(args.imei, args.day,
                                                 args.span):
        body = {'data': {'device_imei': imei, 'from_date': start,
                         'to_date': end, 'offset_log': '0',
                         'record_count': str(args.count)}}
        t0 = time.time()
        try:
            res = client.post('/data-stream/trips/history', json=body)
            took = time.time() - t0
            code = res.status_code
            try:
                payload = res.get_json() or {}
            except Exception:                           # noqa: BLE001
                payload = {}
            message = str(payload.get('message', ''))[:46]
            data = payload.get('data')
            raw = len(data.get('raw_data', [])) if isinstance(data, dict) else 0
            trips = len(data.get('trips_data', [])) if isinstance(data, dict) \
                else 0
        except Exception as error:                      # noqa: BLE001
            took = time.time() - t0
            code, message, raw, trips = 0, f'EXCEPTION {error}'[:46], 0, 0

        if expect == 'rows':
            ok = code == 200 and raw > 0
        else:
            ok = code == 400 and 'no trips' in message.lower()
        # The route checks the device registry and its billing status BEFORE
        # it reads a position, so neither outcome says anything about B2.
        # 'Routing Failed, Device Cant be found' means the imei is absent from
        # Postgres dll_device_basic_data — note that a Cassandra table of the
        # same name holds different rows, which is why a unit can have trips
        # and fixes while check_device still cannot find it.
        low = message.lower()
        billing = ('billing' in low or 'cant be found' in low
                   or 'not-found' in low)

        mark = 'ok ' if ok else ('-- ' if billing else '!! ')
        print(f'   {mark}{label:<24} {start} .. {end}')
        print(f'       HTTP {code}  {message!r}')
        print(f'       raw_data {raw}, trips_data {trips}, {took:.2f}s')
        results.append((label, ok, billing, code, message))
        print()

    print('=' * 66)
    good = [r for r in results if r[1]]
    blocked = [r for r in results if r[2] and not r[1]]
    bad = [r for r in results if not r[1] and not r[2]]
    print(f'   {len(good)} as expected, {len(blocked)} billing-blocked, '
          f'{len(bad)} wrong')

    if blocked:
        print('\n   Those cases prove nothing either way: the route checks the')
        print('   device registry and billing before reading any position, so')
        print('   it never reached the code B2 changed. Re-run them against a')
        print('   unit that find_moving_unit.py reports as billing=running.')
    if bad:
        print('\n   NOT working. Each wrong line means:')
        for label, _ok, _b, code, message in bad:
            if code == 503:
                print(f'     - {label}: 503. The store raised rather than')
                print('       returning empty. If Cassandra is up, the day')
                print('       loop is treating "no rows" as a failure.')
            elif code == 200:
                print(f'     - {label}: 200 with no rows, where none were')
                print('       expected to be found. Check the gate.')
            elif code == 400 and 'no trips' not in message.lower():
                print(f'     - {label}: 400 {message!r} — a different guard '
                      f'(date range, billing, record count) rejected it')
            else:
                print(f'     - {label}: HTTP {code} {message!r}')
        print('\n   data.py has a timestamped .bak beside it if you want the')
        print('   old behaviour back while this is sorted.')
        return 1

    print('\n   B2 works on the live route: recent dates return history where')
    print('   they returned nothing before, an empty window says so honestly')
    print('   rather than erroring, and a 92-day span does not read 92 days.')
    print('\n   Next: B3 switches trips/excel, trips/pdf and')
    print('   trips/history/replay the same way, and B4 replaces the')
    print('   coordinate dedupe with speed-based stop detection.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
