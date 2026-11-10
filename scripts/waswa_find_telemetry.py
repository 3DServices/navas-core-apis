#!/usr/bin/env python3
"""
waswa_find_telemetry.py — where do live positions actually land?

The probe established two things that cannot both be ignored:

  * dll_location_registry's newest row, across every device on the platform,
    is 07-08-2025. It has taken nothing for fourteen months.
  * dll_trips_auditor has 4,991 trips, including some from today.

Trips are still being computed, so something is still receiving positions. It
is not the table waswa_fleet reads. Nothing in this repository writes positions
— the device listener does, outside it — so the only way to find the live table
is to ask the databases what they hold.

This looks for any table, in Postgres or Cassandra, with latitude/longitude
columns, and reports how big it is and how recent. It does not scan: row counts
come from the planner's own estimate, and recency from one indexed lookup.

Read-only.

Usage:
    python scripts/waswa_find_telemetry.py
    python scripts/waswa_find_telemetry.py --imei 350317173603857
"""

import argparse
import sys

import psycopg2

sys.path.insert(0, '.')
from config import DB_LINK, CASSANDRA_KEYSPACE     # noqa: E402

# Columns that mean "this row knows where something was".
_GEO = ('latitude', 'longitude', 'lat', 'lon', 'lng', 'gps', 'cordinates',
        'coordinates', 'location_point')

# Columns worth printing when we find the newest row, in rough order of use.
_WHEN = ('datestamp', 'timestamp', 'date', 'time', 'created', 'received',
         'recorded', 'at')

# Columns that can order a table cheaply (a serial or a clustering key).
_ORDER = ('data_idx', 'idx', 'id', 'row_id', 'seq', 'created_at', 'inserted_at')


def postgres(cur, imei):
    print('\n== Postgres: tables that hold coordinates ' + '=' * 35)
    like = ' OR '.join(["column_name ILIKE %s"] * len(_GEO))
    cur.execute(f"""
        SELECT table_name, STRING_AGG(column_name, ', ' ORDER BY column_name)
          FROM information_schema.columns
         WHERE table_schema = 'public' AND ({like})
         GROUP BY table_name
         ORDER BY table_name""", [f'%{g}%' for g in _GEO])
    candidates = cur.fetchall()
    if not candidates:
        print('   none found.')
        return

    for table, cols in candidates:
        # reltuples is the planner's estimate: instant, and accurate enough to
        # tell a live table from an abandoned one.
        cur.execute("SELECT reltuples::bigint FROM pg_class WHERE relname = %s",
                    (table,))
        row = cur.fetchone()
        est = row[0] if row else -1
        print(f'\n   {table}   (~{est:,} rows)')
        print(f'      geo columns: {cols[:110]}')

        cur.execute("""SELECT column_name FROM information_schema.columns
                        WHERE table_schema='public' AND table_name=%s""", (table,))
        have = [r[0] for r in cur.fetchall()]

        order_by = next((c for c in _ORDER if c in have), None)
        when = [c for c in have if any(w in c.lower() for w in _WHEN)][:4]
        if not order_by or not when:
            print('      (no cheap way to date this one — skipped)')
            continue

        try:
            cur.execute(f'SELECT {", ".join(when)} FROM {table} '
                        f'ORDER BY {order_by} DESC LIMIT 1')
            newest = cur.fetchone()
        except Exception as exc:                    # noqa: BLE001
            cur.connection.rollback()
            print(f'      !! {str(exc).splitlines()[0][:70]}')
            continue
        if newest:
            pairs = ', '.join(f'{c}={v!r}' for c, v in zip(when, newest))
            print(f'      newest row: {pairs[:150]}')
        else:
            print('      empty')

        if imei:
            col = next((c for c in have if 'imei' in c.lower()), None)
            if col:
                try:
                    cur.execute(f'SELECT COUNT(*) FROM {table} WHERE {col} = %s',
                                (str(imei),))
                    print(f'      rows for {imei}: {cur.fetchone()[0]}')
                except Exception as exc:            # noqa: BLE001
                    cur.connection.rollback()
                    print(f'      !! count failed: {str(exc).splitlines()[0][:60]}')


def cassandra():
    print(f'\n== Cassandra ({CASSANDRA_KEYSPACE}): tables that hold coordinates '
          + '=' * 14)
    try:
        from endpoints.devices import get_cassandra_session
        session = get_cassandra_session()
    except Exception as exc:                        # noqa: BLE001
        print(f'   !! could not connect: {str(exc)[:110]}')
        print('   Re-run when it is up; the Postgres findings above stand.')
        return
    if session is None:
        print('   !! no session')
        return

    try:
        rows = session.execute(
            "SELECT table_name, column_name FROM system_schema.columns "
            "WHERE keyspace_name = %s", (CASSANDRA_KEYSPACE,))
    except Exception as exc:                        # noqa: BLE001
        print(f'   !! schema read failed: {str(exc)[:110]}')
        return

    tables = {}
    for r in rows:
        name = str(getattr(r, 'column_name', '') or '')
        if any(g in name.lower() for g in _GEO):
            tables.setdefault(str(getattr(r, 'table_name', '')), []).append(name)

    if not tables:
        print('   no table in this keyspace has coordinate columns.')
        print('   So the live position store is not here either — ask whoever')
        print('   runs the device listener where it writes now.')
        return

    for table, cols in sorted(tables.items()):
        print(f'\n   {table}')
        print(f'      geo columns: {", ".join(sorted(cols))[:110]}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--imei', help='also count rows for this unit in each table')
    args = ap.parse_args()

    conn = psycopg2.connect(DB_LINK)
    try:
        with conn.cursor() as cur:
            postgres(cur, args.imei)
    finally:
        conn.close()

    cassandra()

    print('\n' + '=' * 76)
    print('What to look for: a table with coordinates, a lot of rows, and a')
    print('newest row dated today. That is what waswa_fleet should be reading.')
    print('If nothing is current anywhere, then raw positions are no longer')
    print('stored at all and only trips survive — which caps what Waswa can')
    print('ever answer about routes, and is worth knowing before building more.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
