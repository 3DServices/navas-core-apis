#!/usr/bin/env python3
"""
audit_io_events_stores.py — which store actually holds the IO events?

The B5 audit found the two numbers that matter, for one and the same uid:

    Postgres   2.9s  ->  0 rows   (parallel seq scan, 11 GB, no usable index)
    Cassandra  0.31s ->  1 row

dll_io_events_executed_logs exists in BOTH stores with different contents, and
trips_history reads the Postgres one. That is the shape of B2 exactly: a route
scanning a stale copy while the live data went somewhere else. So the fix is
probably not an index — a faster way to find nothing is still nothing — but I
am not switching a second store on one sample.

Four things decide it, and none can be assumed:

  1. SCHEMA. What the Cassandra table's partition and clustering keys are.
     0.31s with ALLOW FILTERING may be a point lookup or a cluster scan that
     happens to be small today. If io_parent_io_event_uid is not the partition
     key, switching stores trades a Postgres seq scan for a Cassandra one and
     the win evaporates at scale.

  2. COVERAGE. Is the Postgres copy stale in the same way the position table
     was — fine for old uids, empty for recent ones? Sampling uids from an old
     day and a recent day in both stores shows the handover, if there is one.

  3. COLUMNS. The route reads event_uid_executed, event_value_executed and
     data_idx, and orders by data_idx DESC. All three have to exist in
     Cassandra, and data_idx has to be meaningful there — it was NOT
     sequential in dll_location_registry_by_record_ts, which is why
     location_store orders by record_timestamp instead.

  4. REPEATED COST. One 0.31s query may be first-call overhead. Ten in a row
     gives the real per-fix figure, and that decides whether switching stores
     is enough on its own or still needs batching.

Read-only.

Usage:
    python scripts/audit_io_events_stores.py
    python scripts/audit_io_events_stores.py --recent-day 25-09-2026 --old-day 15-08-2025
"""

import argparse
import sys
import time

import psycopg2

sys.path.insert(0, '.')
from config import CASSANDRA_KEYSPACE, DB_LINK          # noqa: E402
from endpoints import location_store                    # noqa: E402

TABLE = 'dll_io_events_executed_logs'


def uids_for(session, imei, day, count):
    rows, _t = location_store.fixes(session, imei, day, day, limit=count)
    return [str(r['io_uid']) for r in rows if r['io_uid']]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--recent-imei', default='862846042622426')
    ap.add_argument('--recent-day', default='25-09-2026')
    ap.add_argument('--old-imei', default='867556044727322')
    ap.add_argument('--old-day', default='15-08-2025')
    ap.add_argument('--count', type=int, default=10)
    args = ap.parse_args()

    from flask import Flask
    app = Flask(__name__)
    app.config['db_link'] = DB_LINK
    with app.app_context():
        from endpoints.devices import get_cassandra_session
        session = get_cassandra_session()
        if session is None:
            print('!! no Cassandra session')
            return 1

        # ── 1. schema ──────────────────────────────────────────────────────
        print('=' * 72)
        print('1. THE CASSANDRA TABLE\'S KEYS  (what may be asked, and how fast)')
        print('=' * 72)
        cols = list(session.execute(
            "SELECT column_name, kind, position, type FROM system_schema.columns "
            "WHERE keyspace_name = %s AND table_name = %s",
            (CASSANDRA_KEYSPACE, TABLE)))
        if not cols:
            print(f'   !! {TABLE} is not in keyspace {CASSANDRA_KEYSPACE}')
            return 1
        part = sorted([c for c in cols if c.kind == 'partition_key'],
                      key=lambda c: c.position)
        clust = sorted([c for c in cols if c.kind == 'clustering'],
                       key=lambda c: c.position)
        print('   partition key : '
              + ', '.join(f'{c.column_name} ({c.type})' for c in part))
        print('   clustering    : '
              + (', '.join(f'{c.column_name} ({c.type})' for c in clust)
                 or '(none)'))
        names = {c.column_name: c.type for c in cols}
        keyed = any(c.column_name == 'io_parent_io_event_uid' for c in part)
        print(f'\n   io_parent_io_event_uid IS the partition key? '
              f'{"YES — point lookup" if keyed else "NO — ALLOW FILTERING scans"}')
        if not keyed:
            print('      -> 0.31s today is not a promise. A scan grows with the')
            print('         table, exactly like the Postgres one we are leaving.')

        # ── 3. columns the route needs ─────────────────────────────────────
        print('\n' + '=' * 72)
        print('3. COLUMNS THE ROUTE READS')
        print('=' * 72)
        for wanted in ('event_uid_executed', 'event_value_executed',
                       'data_idx', 'io_parent_io_event_uid'):
            print(f'   {wanted:<26} '
                  + (names.get(wanted) or 'MISSING — the switch cannot work'))

        # ── 4. repeated cost ───────────────────────────────────────────────
        recent = uids_for(session, args.recent_imei, args.recent_day,
                          args.count)
        old = uids_for(session, args.old_imei, args.old_day, args.count)
        print('\n' + '=' * 72)
        print('4. REPEATED COST IN CASSANDRA  (one sample is not a figure)')
        print('=' * 72)
        if not recent:
            print('   no uids on the recent day; skipping.')
        else:
            times, found = [], 0
            for uid in recent:
                t0 = time.time()
                try:
                    got = list(session.execute(
                        f"SELECT event_uid_executed, event_value_executed, "
                        f"data_idx FROM {TABLE} "
                        f"WHERE io_parent_io_event_uid=%s ALLOW FILTERING;",
                        (uid,)))
                except Exception as error:              # noqa: BLE001
                    print(f'   {uid[:12]}…: ERROR {str(error)[:40]}')
                    continue
                times.append(time.time() - t0)
                found += 1 if got else 0
            if times:
                print(f'   {len(times)} queries: first {times[0]:.2f}s, '
                      f'median {sorted(times)[len(times)//2]:.2f}s, '
                      f'total {sum(times):.2f}s')
                print(f'   uids with rows : {found} of {len(times)}')
                print(f'\n   at this rate a {args.count}-fix page costs '
                      f'{sum(times):.1f}s, and a 500-fix page about '
                      f'{sum(times) / len(times) * 500:.0f}s')

        # ── 2. coverage, both stores, old and recent ───────────────────────
        print('\n' + '=' * 72)
        print('2. COVERAGE: WHO HOLDS WHAT')
        print('=' * 72)
        conn = psycopg2.connect(DB_LINK)
        try:
            with conn.cursor() as cur:
                for label, uids in (('recent  ' + args.recent_day, recent),
                                    ('old     ' + args.old_day, old)):
                    if not uids:
                        print(f'   {label}: no uids to test')
                        continue
                    cur.execute(
                        f"SELECT COUNT(DISTINCT io_parent_io_event_uid) "
                        f"FROM {TABLE} WHERE io_parent_io_event_uid = ANY(%s)",
                        (uids,))
                    pg = cur.fetchone()[0]
                    cass = 0
                    for uid in uids:
                        try:
                            if list(session.execute(
                                    f"SELECT event_uid_executed FROM {TABLE} "
                                    f"WHERE io_parent_io_event_uid=%s "
                                    f"ALLOW FILTERING;", (uid,))):
                                cass += 1
                        except Exception:               # noqa: BLE001
                            pass
                    print(f'   {label}: Postgres {pg}/{len(uids)}, '
                          f'Cassandra {cass}/{len(uids)}')
                print('\n   Postgres row estimate and newest key:')
                cur.execute(f"SELECT c.reltuples::bigint FROM pg_class c "
                            f"WHERE c.relname = '{TABLE}'")
                print(f'      estimated rows : {cur.fetchone()[0]:,}')
                cur.execute(f"SELECT MAX(data_idx), MIN(data_idx) FROM {TABLE}")
                hi, lo = cur.fetchone()
                print(f'      data_idx range : {lo} .. {hi}')
        finally:
            conn.close()

    print('\n' + '=' * 72)
    print('WHAT THIS DECIDES')
    print('=' * 72)
    print('   If Cassandra has the recent uids and Postgres does not, the')
    print('   route is reading a stale copy and B5 becomes a source switch,')
    print('   not an index. If BOTH are empty for recent uids, the IO events')
    print('   are simply not being written any more and this is an ingestion')
    print('   problem, not a read problem — a much bigger finding.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
