#!/usr/bin/env python3
"""
early_stop_check.py — prove the early stop against production data.

location_store.fixes() now reads days newest first and stops when the page is
full, instead of reading the whole window and slicing at the end. On the
busiest unit a 92-day span was 1.2 million dicts to answer a page needing one
day.

The unit tests prove equivalence against a re-implementation of the old
algorithm, but on invented rows. This proves it on the real store, with one
assertion that cannot pass by accident:

    a page of the newest N fixes must be IDENTICAL whether it is asked for
    over one day or over ninety-two

If the newest day holds more distinct coordinates than N — and the measured
unit holds 11,563 — then every row of that page comes from that one day. A
92-day request must return exactly the same rows. If the early stop visits
days in the wrong order, or first-seen-wins keeps the wrong occurrence, or a
boundary between local days is mishandled, the two pages differ.

It also times both, because the point of the change was cost.

Read-only.

Usage:
    python scripts/early_stop_check.py --imei 353742375512035 --day 01-10-2026
"""

import argparse
import sys
import time
from datetime import datetime, timedelta

sys.path.insert(0, '.')
from config import DB_LINK                              # noqa: E402
from endpoints import location_store                    # noqa: E402

PAGE = 50


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--imei', required=True)
    ap.add_argument('--day', required=True,
                    help='DD-MM-YYYY, a busy day; it becomes the window end')
    ap.add_argument('--page', type=int, default=PAGE)
    args = ap.parse_args()
    imei = ''.join(str(args.imei).split())
    end = datetime.strptime(args.day, '%d-%m-%Y').date()

    from flask import Flask
    app = Flask(__name__)
    app.config['db_link'] = DB_LINK
    with app.app_context():
        from endpoints.devices import get_cassandra_session
        session = get_cassandra_session()
        if session is None:
            print('!! no Cassandra session')
            return 1

        def ask(span_days, limit, offset=0):
            start = end - timedelta(days=span_days - 1)
            t0 = time.time()
            rows, truncated = location_store.fixes(
                session, imei, start.strftime('%d-%m-%Y'),
                end.strftime('%d-%m-%Y'), limit=limit, offset=offset)
            return rows, truncated, time.time() - t0

        print(f'unit {imei}, window ends {args.day}, page size {args.page}\n')

        one, _t1, took_one = ask(1, args.page)
        print(f'   1-day window  : {len(one):>5} row(s)  {took_one:>6.2f}s')
        if len(one) < args.page:
            print(f'\n!! that day returned fewer than {args.page} rows, so the')
            print('   page is not contained in it and this check proves')
            print('   nothing. Pick a busier day.')
            return 1

        wide, truncated, took_wide = ask(92, args.page)
        print(f'   92-day window : {len(wide):>5} row(s)  {took_wide:>6.2f}s'
              + ('  [span truncated]' if truncated else ''))

        def shape(rows):
            return [(r['lon'], r['lat'], r['at_utc'], r['row_index'])
                    for r in rows]

        print('\n' + '=' * 66)
        print('IS THE PAGE THE SAME OVER ONE DAY AND OVER NINETY-TWO?')
        print('=' * 66)
        if shape(one) == shape(wide):
            print('   IDENTICAL — same coordinates, same timestamps, same order,')
            print('   same row_index.')
            ok = True
        else:
            ok = False
            print('   !! THEY DIFFER. The early stop is wrong; do not switch')
            print('      any route.')
            for i, (a, b) in enumerate(zip(shape(one), shape(wide))):
                if a != b:
                    print(f'      first difference at row {i + 1}:')
                    print(f'        1-day  : {a}')
                    print(f'        92-day : {b}')
                    break
            if len(one) != len(wide):
                print(f'      lengths differ: {len(one)} vs {len(wide)}')

        # A deep page too: offset exercises the "collect offset+limit" path.
        deep_one, _t, _ = ask(1, args.page, offset=args.page * 3)
        deep_wide, _t, _ = ask(92, args.page, offset=args.page * 3)
        print()
        if shape(deep_one) == shape(deep_wide):
            print(f'   offset {args.page * 3}: identical as well '
                  f'({len(deep_one)} rows)')
        else:
            ok = False
            print(f'   !! offset {args.page * 3} DIFFERS — pagination under the')
            print('      early stop is wrong.')

        print('\n' + '=' * 66)
        print('COST')
        print('=' * 66)
        print(f'   92-day page took {took_wide:.2f}s against {took_one:.2f}s '
              f'for one day.')
        if took_wide < max(1.0, took_one * 4):
            print('   The wide window is not paying for the days it skipped,')
            print('   which is the whole point of the change.')
        else:
            print('   The wide window is still reading far more than the page')
            print('   needs. The early stop may not be engaging — check that')
            print('   data.py passes a limit and leaves newest_first alone.')

        big, _t, took_big = ask(92, 15000)
        print(f'\n   92 days at the API cap (limit 15000): {len(big)} rows '
              f'in {took_big:.2f}s')

        print('\n' + '=' * 66)
        if ok:
            print('   The early stop is faithful on production data. Together')
            print('   with the 48 unit tests, B2 is ready:')
            print('\n     python scripts/patch_b2_history.py --apply --b1-passed')
        else:
            print('   Do not apply B2. Send this output back.')
        return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
