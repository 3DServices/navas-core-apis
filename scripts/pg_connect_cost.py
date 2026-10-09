#!/usr/bin/env python3
"""
pg_connect_cost.py -- is a 2-second Postgres connect network latency, or the
server?

The trips/history profile put psycopg2.connect at 4.07s of a 10.84s request:
~2.03s per connection, twice. That is 100x what a healthy local connect costs,
so it needs an explanation before anyone changes code.

Two candidate explanations, and they call for opposite fixes:

  LATENCY  A connect is ~6-8 round trips (TCP handshake, SSL negotiation,
           startup packet, auth). From Kampala to a droplet at ~250ms RTT that
           alone is 1.5-2s, with nothing wrong on the server. In production,
           where the app is presumably co-located with the database, the same
           code would cost milliseconds -- and this profile would say almost
           nothing about production.

  SERVER   The connect is slow regardless of distance: a backend that is slow
           to fork, a proc array sized for max_connections = 50000, memory
           pressure from work_mem = 10GB (B11), or saturation.

The test: a trivial query on an ALREADY OPEN connection costs one round trip.
So

    connect_time / query_time  ~=  the number of round trips in a connect

If that ratio lands near 6-10, the connect is latency-bound and the honest
conclusion is "measure again on the server". If the ratio is far higher, the
round trips are not the story and the server is.

Read-only: it opens connections and runs SELECT 1. Nothing is written.

Usage:
    python scripts/pg_connect_cost.py
    python scripts/pg_connect_cost.py --samples 10
"""

import argparse
import statistics
import sys
import time as _time

sys.path.insert(0, '.')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--samples', type=int, default=5)
    args = ap.parse_args()

    import psycopg2
    from config import DB_LINK

    print('samples: %d' % args.samples)
    print('')

    # --- 1. full connect, repeatedly
    connects = []
    for _ in range(args.samples):
        began = _time.time()
        conn = psycopg2.connect(DB_LINK)
        connects.append(_time.time() - began)
        conn.close()

    # --- 2. one round trip on an already open connection
    conn = psycopg2.connect(DB_LINK)
    queries = []
    for _ in range(args.samples * 4):
        began = _time.time()
        with conn.cursor() as cur:
            cur.execute('SELECT 1')
            cur.fetchone()
        queries.append(_time.time() - began)

    # --- 3. a query that does real server work, to separate "slow link" from
    #        "slow server": this one plans and scans a catalog.
    catalogs = []
    for _ in range(args.samples):
        began = _time.time()
        with conn.cursor() as cur:
            cur.execute('SELECT count(*) FROM pg_stat_activity')
            cur.fetchone()
        catalogs.append(_time.time() - began)

    # --- 4. the server's own view of itself
    with conn.cursor() as cur:
        cur.execute("SELECT current_setting('max_connections'), "
                    "       current_setting('work_mem'), "
                    "       (SELECT count(*) FROM pg_stat_activity)")
        max_conn, work_mem, active = cur.fetchone()
    conn.close()

    c_med = statistics.median(connects)
    q_med = statistics.median(queries)
    k_med = statistics.median(catalogs)
    ratio = c_med / q_med if q_med else 0

    print('  %-32s %7.1f ms  (min %.0f, max %.0f)'
          % ('full connect', c_med * 1000, min(connects) * 1000,
             max(connects) * 1000))
    print('  %-32s %7.1f ms  <- one round trip'
          % ('SELECT 1 on an open conn', q_med * 1000))
    print('  %-32s %7.1f ms' % ('count(*) pg_stat_activity', k_med * 1000))
    print('')
    print('  %-32s %7.1f' % ('connect / round trip', ratio))
    print('')
    print('  %-32s %s' % ('server max_connections', max_conn))
    print('  %-32s %s' % ('server work_mem', work_mem))
    print('  %-32s %s' % ('backends currently open', active))
    print('')

    if q_med > 0.080:
        print('  >> one round trip costs %.0f ms. This link is slow, and a'
              % (q_med * 1000))
        print('     connect is several round trips, so most of the 2s is')
        print('     DISTANCE, not the server. The production number must be')
        print('     measured ON the server before any code is changed for it.')
    if 4 <= ratio <= 12:
        print('  >> the ratio (%.1f) is about what a connect\'s round trips'
              % ratio)
        print('     cost. Consistent with a latency-bound connect.')
    elif ratio > 12:
        print('  >> the ratio (%.1f) is far more than a connect\'s round trips'
              % ratio)
        print('     explain. Something server-side is slow to hand out a')
        print('     backend -- max_connections = %s is the first suspect,'
              % max_conn)
        print('     which is exactly B11.')
    if q_med <= 0.080 and c_med > 0.5:
        print('  >> the link is fast but connects are slow. That is the')
        print('     server, not the distance.')

    print('')
    print('  Either way, 2 connects per request is a code fact: a pool or a')
    print('  reused connection removes them wherever this runs.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
