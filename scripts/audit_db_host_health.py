#!/usr/bin/env python3
"""
audit_db_host_health.py — is 165.232.128.208 dropping connections?

Two failures in the last few minutes, on one host:

    Cassandra  :9042  OperationTimedOut on the cluster handshake
    Postgres   :5432  "server closed the connection unexpectedly" at connect

The Postgres one landed at data.py:1141 — trips_history's own connect, a line
B7 never touched — and B7's own change is visibly working (2 connections per
request instead of 3, counted on both a successful and a failed request).
Both services sit on the same box, and both failed during ~90 seconds of
back-to-back requests. That points at the host.

Pointing is not proving. B7 did change connection lifecycle, so this measures
the host directly rather than letting me argue from circumstance:

  1. HAS POSTGRES RESTARTED? pg_postmaster_start_time() is decisive. "server
     closed the connection unexpectedly" is exactly what a restart or an OOM
     kill looks like from the client side. If uptime is minutes rather than
     days, the host is the story and B7 is exonerated.

  2. DOES REPEATED CONNECTING FAIL? Ten sequential connects, each timed, each
     closed properly. If some fail, the host refuses connections under
     ordinary load and no application change fixes that.

  3. WHAT IS max_connections REALLY? It reported 50,000, which is not a
     plausible deliberate setting — a normal Postgres is 100, and a value
     that high with limited RAM makes the server fail in confusing ways
     rather than cleanly refusing. Worth confirming alongside the memory
     settings it has to coexist with.

  4. IS CASSANDRA'S HANDSHAKE RELIABLE? Three cluster connects, timed. This
     is the B9 cold-start question and the same host.

Read-only. Opens and closes its own connections and terminates nobody else's.

Usage:
    python scripts/audit_db_host_health.py
"""

import argparse
import sys
import time

import psycopg2

sys.path.insert(0, '.')
from config import DB_LINK                              # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--connects', type=int, default=10)
    ap.add_argument('--cassandra-tries', type=int, default=3)
    args = ap.parse_args()

    print('=' * 70)
    print('1. HAS POSTGRES RESTARTED RECENTLY?')
    print('=' * 70)
    try:
        conn = psycopg2.connect(DB_LINK)
        with conn.cursor() as cur:
            cur.execute("SELECT pg_postmaster_start_time(), "
                        "now() - pg_postmaster_start_time(), version()")
            started, uptime, version = cur.fetchone()
            print(f'   started : {started}')
            print(f'   uptime  : {uptime}')
            print(f'   version : {str(version)[:60]}')
            if uptime.total_seconds() < 3600:
                print('\n   -> RESTARTED WITHIN THE HOUR. "server closed the')
                print('      connection unexpectedly" is what a restart looks')
                print('      like from the client. The host is the cause, not')
                print('      any application change.')
            else:
                print('\n   -> no recent restart, so a dropped connection is')
                print('      not explained by the server going down.')

            print('\n' + '=' * 70)
            print('3. SETTINGS THAT HAVE TO COEXIST')
            print('=' * 70)
            for name in ('max_connections', 'shared_buffers', 'work_mem',
                         'superuser_reserved_connections',
                         'idle_in_transaction_session_timeout',
                         'statement_timeout', 'tcp_keepalives_idle'):
                try:
                    cur.execute(f'SHOW {name}')
                    print(f'   {name:<38} {cur.fetchone()[0]}')
                except Exception as error:              # noqa: BLE001
                    conn.rollback()
                    print(f'   {name:<38} ? ({str(error)[:28]})')
            cur.execute("SELECT count(*) FROM pg_stat_activity")
            print(f'   {"connections right now":<38} {cur.fetchone()[0]}')
        conn.close()
    except Exception as error:                          # noqa: BLE001
        print(f'   !! could not connect at all: {str(error)[:90]}')
        print('      That alone answers the question: the host is refusing.')
        return 1

    print('\n' + '=' * 70)
    print(f'2. {args.connects} SEQUENTIAL CONNECTS, EACH CLOSED')
    print('=' * 70)
    times, failures = [], []
    for attempt in range(1, args.connects + 1):
        t0 = time.time()
        try:
            c = psycopg2.connect(DB_LINK)
            took = time.time() - t0
            c.close()
            times.append(took)
            print(f'   {attempt:>3}: {took:>6.2f}s  ok')
        except Exception as error:                      # noqa: BLE001
            took = time.time() - t0
            failures.append((attempt, str(error)[:60]))
            print(f'   {attempt:>3}: {took:>6.2f}s  FAILED  {str(error)[:52]}')
    if times:
        print(f'\n   succeeded {len(times)}/{args.connects}, '
              f'min {min(times):.2f}s, median '
              f'{sorted(times)[len(times)//2]:.2f}s, max {max(times):.2f}s')
    if failures:
        print(f'   FAILED {len(failures)}: '
              f'{[a for a, _m in failures]}')
        print('\n   -> the host refuses connections under ordinary sequential')
        print('      load. No application change fixes that; it is a server')
        print('      or network problem and it explains the 500.')
    else:
        print('\n   -> every connect succeeded. The 500 was intermittent, so')
        print('      the route needs to survive it rather than assume a')
        print('      connect always works.')

    print('\n' + '=' * 70)
    print(f'4. CASSANDRA HANDSHAKE, {args.cassandra_tries} TIMES  (ticket B9)')
    print('=' * 70)
    from flask import Flask
    app = Flask(__name__)
    app.config['db_link'] = DB_LINK
    for attempt in range(1, args.cassandra_tries + 1):
        with app.app_context():
            import endpoints.data as data_module
            # force a fresh cluster each time, so this measures the handshake
            # rather than the cached session
            data_module._cassandra_session = None
            data_module._cassandra_cluster = None
            t0 = time.time()
            try:
                session = data_module.get_cassandra_session()
                took = time.time() - t0
                print(f'   {attempt:>3}: {took:>6.2f}s  '
                      + ('ok' if session is not None else 'RETURNED None'))
            except Exception as error:                  # noqa: BLE001
                print(f'   {attempt:>3}: {time.time() - t0:>6.2f}s  '
                      f'raised {str(error)[:44]}')

    print('\n' + '=' * 70)
    print('WHAT THIS SETTLES')
    print('=' * 70)
    print('   A recent Postgres restart, or connects failing here, means the')
    print('   500 is the host and B7 is cleared. If both look healthy, the')
    print('   failure was a transient the route should tolerate — and either')
    print('   way trips_history should not answer a dropped connect with a')
    print('   raw psycopg2 message and a 500.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
