#!/usr/bin/env python3
"""
audit_io_events_query.py — why does one query cost 4.5 seconds?

The B5 baseline measured 13 queries for a 10-fix page, taking 48.94s. Ten of
those are the same statement, once per fix:

    SELECT event_uid_executed, event_value_executed, data_idx
      FROM dll_io_events_executed_logs
     WHERE io_parent_io_event_uid = %s
     ORDER BY data_idx DESC

That is ~4.5s each, which is not a round-trip cost. It is the cost of the
query itself. This establishes why, from the database rather than from a guess:

  1. how big the table is
  2. what indexes exist on it
  3. what the planner actually does with this statement (EXPLAIN ANALYZE)
  4. how long it really takes, three times, so one cold run is not the whole
     story
  5. whether any of the day's fixes HAVE io events at all — because the
     baseline says none did, which means Config_Sources never ran and the
     per-fix Cassandra scans I was going to optimise never happened
  6. whether the Cassandra copy of the same table answers faster, since
     Config_Sources reads it from there while this route reads Postgres

Nothing is written. EXPLAIN ANALYZE runs the SELECT; it is read-only.

Usage:
    python scripts/audit_io_events_query.py --imei 862846042622426 --day 25-09-2026
"""

import argparse
import sys
import time

import psycopg2

sys.path.insert(0, '.')
from config import CASSANDRA_KEYSPACE, DB_LINK          # noqa: E402
from endpoints import location_store                    # noqa: E402

THE_QUERY = ("SELECT event_uid_executed, event_value_executed, data_idx "
             "FROM dll_io_events_executed_logs "
             "WHERE io_parent_io_event_uid = %s ORDER BY data_idx DESC")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--imei', default='862846042622426')
    ap.add_argument('--day', default='25-09-2026')
    ap.add_argument('--count', type=int, default=10)
    args = ap.parse_args()

    # The same fixes the route would have worked on, so the uids are real.
    from flask import Flask
    app = Flask(__name__)
    app.config['db_link'] = DB_LINK
    with app.app_context():
        from endpoints.devices import get_cassandra_session
        session = get_cassandra_session()
        rows, _t = location_store.fixes(session, args.imei, args.day, args.day,
                                        limit=args.count)
    uids = [r['io_uid'] for r in rows]
    print(f'unit {args.imei}, day {args.day}: {len(rows)} fix(es)')
    print(f'record_io_events_uid present on {sum(1 for u in uids if u)} '
          f'of {len(uids)}')
    sample = next((u for u in uids if u), None)
    print(f'sample uid: {sample!r}\n')

    conn = psycopg2.connect(DB_LINK)
    try:
        with conn.cursor() as cur:
            print('=' * 70)
            print('1. TABLE SIZE')
            print('=' * 70)
            cur.execute("""
                SELECT c.reltuples::bigint,
                       pg_size_pretty(pg_total_relation_size(c.oid))
                  FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                 WHERE c.relname = 'dll_io_events_executed_logs'
                   AND n.nspname = 'public'""")
            got = cur.fetchone()
            if got:
                print(f'   estimated rows : {got[0]:,}')
                print(f'   total size     : {got[1]}')
            else:
                print('   !! table not found in public schema')

            print('\n' + '=' * 70)
            print('2. INDEXES')
            print('=' * 70)
            cur.execute("SELECT indexname, indexdef FROM pg_indexes "
                        "WHERE tablename = 'dll_io_events_executed_logs'")
            idx = cur.fetchall()
            if not idx:
                print('   NONE. Every lookup is a full sequential scan.')
            for name, definition in idx:
                print(f'   {name}')
                print(f'      {definition}')
            covers = any('io_parent_io_event_uid' in d for _n, d in idx)
            print(f'\n   an index on io_parent_io_event_uid? '
                  f'{"yes" if covers else "NO — this is the 4.5 seconds"}')

            print('\n' + '=' * 70)
            print('3. COLUMN TYPES  (a text/bigint mismatch defeats an index)')
            print('=' * 70)
            cur.execute("""
                SELECT column_name, data_type FROM information_schema.columns
                 WHERE table_name = 'dll_io_events_executed_logs'
                   AND column_name IN ('io_parent_io_event_uid',
                                       'event_uid_executed', 'data_idx')
                 ORDER BY column_name""")
            for name, kind in cur.fetchall():
                print(f'   {name:<26} {kind}')

            if sample is None:
                print('\n   no usable uid on these fixes; skipping 4 and 5.')
            else:
                print('\n' + '=' * 70)
                print('4. WHAT THE PLANNER DOES')
                print('=' * 70)
                cur.execute('EXPLAIN (ANALYZE, BUFFERS) ' + THE_QUERY,
                            (str(sample),))
                for (line,) in cur.fetchall():
                    print(f'   {line}')

                print('\n' + '=' * 70)
                print('5. HOW LONG, THREE TIMES')
                print('=' * 70)
                for attempt in range(1, 4):
                    t0 = time.time()
                    cur.execute(THE_QUERY, (str(sample),))
                    n = cur.rowcount
                    print(f'   run {attempt}: {time.time() - t0:>6.2f}s  '
                          f'({n} row(s))')

                print('\n' + '=' * 70)
                print('6. DO ANY OF THE DAY\'S FIXES HAVE IO EVENTS?')
                print('=' * 70)
                cur.execute(
                    "SELECT COUNT(DISTINCT io_parent_io_event_uid) "
                    "FROM dll_io_events_executed_logs "
                    "WHERE io_parent_io_event_uid = ANY(%s)",
                    ([str(u) for u in uids if u],))
                hits = cur.fetchone()[0]
                print(f'   {hits} of {sum(1 for u in uids if u)} uid(s) have '
                      f'rows')
                if hits == 0:
                    print('   -> none. Config_Sources never runs for this')
                    print('      request, so the config-cache stage would')
                    print('      save nothing here. Its cost is unproven.')

                print('\n   and the SAME lookup batched into one statement:')
                t0 = time.time()
                cur.execute(
                    "SELECT io_parent_io_event_uid, event_uid_executed, "
                    "event_value_executed, data_idx "
                    "FROM dll_io_events_executed_logs "
                    "WHERE io_parent_io_event_uid = ANY(%s) "
                    "ORDER BY data_idx DESC",
                    ([str(u) for u in uids if u],))
                batched = cur.fetchall()
                took = time.time() - t0
                print(f'   one ANY() query for all {len(uids)} uid(s): '
                      f'{took:.2f}s, {len(batched)} row(s)')
    finally:
        conn.close()

    print('\n' + '=' * 70)
    print('7. IS THE CASSANDRA COPY FASTER?')
    print('=' * 70)
    if sample is None:
        print('   skipped — no uid.')
    else:
        with app.app_context():
            from endpoints.devices import get_cassandra_session as gcs
            s = gcs()
            try:
                t0 = time.time()
                got = list(s.execute(
                    "SELECT event_uid_executed, event_value_executed "
                    "FROM dll_io_events_executed_logs "
                    "WHERE io_parent_io_event_uid=%s ALLOW FILTERING;",
                    (str(sample),)))
                print(f'   Cassandra, ALLOW FILTERING: '
                      f'{time.time() - t0:.2f}s, {len(got)} row(s)')
                print('   (Config_Sources reads it from here, while the route')
                print('    reads Postgres. Same name, possibly different rows —')
                print('    compare before relying on either.)')
            except Exception as error:                  # noqa: BLE001
                print(f'   refused: {str(error)[:70]}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
