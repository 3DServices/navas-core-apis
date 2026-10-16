#!/usr/bin/env python3
"""
waswa_data_probe.py — is the telemetry actually there?

waswa_fleet_check showed all five units with zero trips, zero distance and no
last fix. That has two completely different explanations and they need
opposite fixes:

  * the query is wrong  -> fix waswa_fleet.py
  * the units are dormant -> fix nothing; Waswa is right to say so

The position query in waswa_fleet._points is byte-for-byte the same table,
columns and date predicate that data.py has used in production for a long
time, so dormancy is the likelier answer. This settles it by going round the
query entirely: no date filter, no IMEI formatting, just counts.

Read-only.

Usage:
    python scripts/waswa_data_probe.py --client CLIENT_UID
    python scripts/waswa_data_probe.py --imei 862846042593213
"""

import argparse
import sys
from datetime import datetime

import psycopg2

sys.path.insert(0, '.')
from config import DB_LINK                        # noqa: E402
from endpoints import waswa_fleet                 # noqa: E402


def probe_positions(cur, imeis):
    print('\n== dll_location_registry, no date filter ' + '=' * 36)
    print(f'   {"imei":<17} {"rows":>9}  {"earliest":<12} {"latest":<12}')
    silent = []
    for imei in imeis:
        cur.execute("""
            SELECT COUNT(*),
                   MIN(TO_DATE(local_system_datestamp, 'DD-MM-YYYY')),
                   MAX(TO_DATE(local_system_datestamp, 'DD-MM-YYYY'))
              FROM dll_location_registry
             WHERE data_device_imei = %s""", (str(imei),))
        rows, lo, hi = cur.fetchone()
        print(f'   {imei:<17} {rows:>9}  {str(lo or "-"):<12} {str(hi or "-"):<12}')
        if not rows:
            silent.append(imei)

    print()
    if silent:
        print(f'   {len(silent)} of {len(imeis)} unit(s) have NEVER logged a position.')
        print('   For those, Waswa saying "no positions in that range" is correct.')
    live = [i for i in imeis if i not in silent]
    if live:
        print(f'   {len(live)} unit(s) DO have history. If waswa_fleet still returns')
        print('   nothing for them, the date window is the fault, not the query:')
        print('   re-run the fleet check with --days covering the latest date above.')
    return silent


def probe_table_recency(cur):
    """Is the position pipeline alive at all, for anybody?

    Ordered by data_idx rather than by date: data_idx is the insertion order,
    so the newest row is one index lookup. MAX over a text date would mean
    casting every row in the table.
    """
    print('\n== Is the position pipeline still running? ' + '=' * 35)
    try:
        cur.execute("SELECT local_system_datestamp, local_system_timestamp, "
                    "       data_device_imei "
                    "FROM dll_location_registry ORDER BY data_idx DESC LIMIT 1")
        row = cur.fetchone()
    except Exception as exc:                        # noqa: BLE001
        cur.connection.rollback()
        print(f'   !! {str(exc).splitlines()[0][:80]}')
        return
    if not row:
        print('   dll_location_registry is EMPTY for every device.')
        return
    date_text, time_text, imei = row
    print(f'   newest row in the whole table : {date_text} {time_text}')
    print(f'   written for                   : {imei}')
    print()
    print('   If that date is recent, the pipeline is fine and the units you')
    print('   probed are simply not sending positions — Waswa is right to say so.')
    print('   If it is old, position ingestion stopped platform-wide, and that')
    print('   is a device-listener problem, not an assistant problem.')


def probe_trips(cur, imeis):
    """dll_trips_auditor — the table the console's Trips report actually reads."""
    print('\n== dll_trips_auditor (what the Trips report uses) ' + '=' * 28)
    try:
        cur.execute("SELECT COUNT(*) FROM dll_trips_auditor")
        total = cur.fetchone()[0]
    except Exception as exc:                        # noqa: BLE001
        cur.connection.rollback()
        print(f'   !! cannot read dll_trips_auditor: {str(exc).splitlines()[0][:70]}')
        return
    print(f'   rows in the table, all devices : {total}')

    print(f'\n   {"imei":<17} {"trips":>7} {"ended":>7}  {"earliest":<12} {"latest":<12}')
    populated = []
    for imei in imeis:
        try:
            cur.execute("""
                SELECT COUNT(*),
                       COUNT(*) FILTER (WHERE trip_status = 'ended'),
                       MIN(trip_date), MAX(trip_date)
                  FROM dll_trips_auditor WHERE device_imei = %s""", (str(imei),))
            n, ended, lo, hi = cur.fetchone()
        except Exception as exc:                    # noqa: BLE001
            cur.connection.rollback()
            print(f'   {imei:<17} !! {str(exc).splitlines()[0][:50]}')
            continue
        print(f'   {imei:<17} {n:>7} {ended:>7}  '
              f'{str(lo or "-")[:10]:<12} {str(hi or "-")[:10]:<12}')
        if ended:
            populated.append(imei)

    print()
    if populated:
        print(f'   {len(populated)} unit(s) have finished trips here. Waswa should read')
        print('   THIS table, so that it and the Trips report can never disagree.')
    elif total:
        print('   The table has trips for other devices but none for these units.')
    else:
        print('   The table is empty platform-wide; trips are not being recorded.')


def probe_heartbeats(imeis):
    """The heartbeat lives in Cassandra, and the raw text is what matters —
    _stamp can only parse a format it is shown."""
    print('\n== dll_pulse_status_registry, raw text ' + '=' * 38)
    try:
        session = waswa_fleet._cassandra()
    except Exception as exc:                        # noqa: BLE001
        print(f'   !! could not reach Cassandra: {exc}')
        return
    stmt = session.prepare(
        "SELECT last_heartbeat_date, last_heartbeat_time "
        "FROM dll_pulse_status_registry WHERE device_data_imei = ? LIMIT 1")
    print(f'   {"imei":<17} {"date (raw)":<14} {"time (raw)":<14} parsed?')
    for imei in imeis:
        try:
            row = session.execute(stmt, (str(imei),)).one()
        except Exception as exc:                    # noqa: BLE001
            print(f'   {imei:<17} !! {str(exc).splitlines()[0][:50]}')
            continue
        if row is None:
            print(f'   {imei:<17} {"(no row)":<14} {"":<14} never reported')
            continue
        d = getattr(row, 'last_heartbeat_date', None)
        t = getattr(row, 'last_heartbeat_time', None)
        parsed = waswa_fleet._stamp(d, t)
        verdict = str(parsed) if parsed else '!! UNPARSEABLE — fix _stamp'
        print(f'   {imei:<17} {str(d):<14} {str(t):<14} {verdict}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--client', help='probe every unit on this client')
    ap.add_argument('--imei', action='append', help='probe this unit (repeatable)')
    args = ap.parse_args()

    imeis = list(args.imei or [])
    register_down = None

    if args.client:
        # The unit list lives in Cassandra. If that is down, say so plainly and
        # carry on with everything Postgres can answer by itself — an outage in
        # one store is not a reason to learn nothing about the other.
        from flask import Flask
        app = Flask(__name__)
        app.config['db_link'] = DB_LINK
        try:
            with app.app_context():
                scope = waswa_fleet.build_scope('PROBE', args.client, is_staff=True)
                fleet = waswa_fleet.unit_find(scope=scope)
            for u in (fleet.get('units') or []):
                if u.get('imei') and u['imei'] not in imeis:
                    imeis.append(u['imei'])
            if fleet.get('unavailable'):
                register_down = fleet.get('reason')
        except Exception as error:                  # noqa: BLE001
            register_down = f'{error.__class__.__name__}: {error}'

    if register_down:
        print('\n!! The vehicle register (Cassandra dll_device_basic_data) could')
        print(f'   not be read: {str(register_down)[:120]}')
        print('   The per-unit checks below need it; the table-wide ones do not.')
        if not imeis:
            print('   To check specific units anyway, pass them directly, e.g.')
            print('     --imei 862846042593213 --imei 867556044727322')

    print(f'\nprobing {len(imeis)} unit(s) at {datetime.now():%Y-%m-%d %H:%M}')
    conn = psycopg2.connect(DB_LINK)
    try:
        with conn.cursor() as cur:
            # Table-wide first: these need no IMEI, and when the register is
            # down they are the only thing that will run.
            probe_table_recency(cur)
            probe_trips(cur, imeis)
            if imeis:
                probe_positions(cur, imeis)
    finally:
        conn.close()

    if imeis:
        probe_heartbeats(imeis)

    print('\nDone.')
    return 2 if register_down and not imeis else 0


if __name__ == '__main__':
    sys.exit(main())
