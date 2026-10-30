#!/usr/bin/env python3
"""
audit_b5_remaining.py — the last two unknowns, before any code is written.

Three audits have each overturned the previous B5 plan. What is established:

  * the route's IO-events gate reads a Postgres table that has never held
    these uids (0/10 recent, 0/3 old), so the gate has always been false
  * Cassandra holds them, keyed on the partition key, 0.30s per lookup
  * dll_io_events_config — the IO NAME table — has ZERO rows, so no channel
    id can ever resolve and every event would hit None[0]
  * the vendor is xirgo_global, so IO_ID_Found is never assigned -> NameError
  * data_idx orders differently as text than as a number

Two things are still assumed, and both change what B5 is worth doing:

  1. IS dll_device_local_configs POPULATED?
     Config_Sources is the only reason to open the gate — it is what yields
     ignition, mileage, fuel and driver ID, and it reads a DIFFERENT table
     from the empty one. If it has rows for these devices, opening the gate
     restores real data. If it is empty too, opening the gate yields only
     fallback values (ignition inferred from speed, driver 'un_registered'),
     and B5 is purely a speed fix with no data story. I am not claiming
     either until this says which.

  2. WHERE DOES THE REST OF THE TIME GO?
     The baseline was 48.94s. Ten IO-events scans at ~2.9s is ~29s. The other
     ~20s is in no counted query. cProfile over the real request attributes
     it. Fixing 29s and shipping a 20s route would be fixing the half I
     happened to measure.

Read-only. Nothing is written.

Usage:
    python scripts/audit_b5_remaining.py
"""

import argparse
import cProfile
import io
import pstats
import sys

sys.path.insert(0, '.')
from config import CASSANDRA_KEYSPACE, DB_LINK          # noqa: E402

PARAMETERS = ('ignition_detection', 'driver_detection', 'fuel_level',
              'mileage_reading')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--imei', default='862846042622426')
    ap.add_argument('--day', default='25-09-2026')
    ap.add_argument('--count', type=int, default=10)
    ap.add_argument('--others', default='867556044656851,862846042622160',
                    help='more imeis to check config coverage for')
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

        print('=' * 72)
        print('1. IS dll_device_local_configs POPULATED?')
        print('=' * 72)
        cols = list(session.execute(
            "SELECT column_name, kind, position, type FROM system_schema.columns "
            "WHERE keyspace_name=%s AND table_name='dll_device_local_configs'",
            (CASSANDRA_KEYSPACE,)))
        if not cols:
            print('   !! the table is not in this keyspace at all.')
        else:
            part = [c.column_name for c in sorted(cols, key=lambda c: c.position)
                    if c.kind == 'partition_key']
            print(f'   partition key : {part}')
            print(f'   columns       : {sorted(c.column_name for c in cols)}')

            try:
                any_rows = list(session.execute(
                    "SELECT local_device_imei, config_parameter, "
                    "config_param_data_source_uid "
                    "FROM dll_device_local_configs LIMIT 5;"))
                print(f'\n   a LIMIT 5 peek returned {len(any_rows)} row(s):')
                for r in any_rows:
                    print(f'      imei={r.local_device_imei!r} '
                          f'param={r.config_parameter!r} '
                          f'source={r.config_param_data_source_uid!r}')
                if not any_rows:
                    print('      -> EMPTY. Config_Sources can only ever return')
                    print('         its fallbacks, so opening the gate restores')
                    print('         no real data. B5 becomes a pure speed fix.')
            except Exception as error:                  # noqa: BLE001
                print(f'   peek refused: {str(error)[:60]}')

            print('\n   per device and parameter, as Config_Sources asks:')
            imeis = [args.imei] + [i.strip() for i in args.others.split(',')
                                   if i.strip()]
            for imei in imeis:
                hits = []
                for parameter in PARAMETERS:
                    try:
                        got = list(session.execute(
                            "SELECT config_param_data_source_uid "
                            "FROM dll_device_local_configs "
                            "WHERE config_parameter=%s AND "
                            "local_device_imei=%s ALLOW FILTERING;",
                            (parameter, str(imei))))
                    except Exception:                   # noqa: BLE001
                        got = []
                    hits.append(f'{parameter.split("_")[0]}='
                                f'{len(got)}')
                print(f'      {imei}: ' + '  '.join(hits))
            print('\n   (Config_Sources acts only when a lookup returns')
            print('    EXACTLY 1 row; 0 and 2+ both fall back.)')

    print('\n' + '=' * 72)
    print('2. WHERE THE 48.94 SECONDS GO')
    print('=' * 72)
    from app import app as flask_app
    client = flask_app.test_client()
    body = {'data': {'device_imei': args.imei, 'from_date': args.day,
                     'to_date': args.day, 'offset_log': '0',
                     'record_count': str(args.count)}}

    profiler = cProfile.Profile()
    profiler.enable()
    res = client.post('/data-stream/trips/history', json=body)
    profiler.disable()
    print(f'   HTTP {res.status_code}\n')

    buffer = io.StringIO()
    stats = pstats.Stats(profiler, stream=buffer).sort_stats('cumulative')
    stats.print_stats(22)
    text = buffer.getvalue()
    # keep the table, drop the long preamble
    started = False
    for line in text.splitlines():
        if line.strip().startswith('ncalls'):
            started = True
        if started:
            print('   ' + line[:150])

    print('\n' + '=' * 72)
    print('WHAT THIS SETTLES')
    print('=' * 72)
    print('   If the config table has rows for these devices, B5 restores')
    print('   ignition/mileage/fuel/driver AND removes ~29s. If it does not,')
    print('   B5 is a speed and correctness fix only — still worth doing, but')
    print('   I will not describe it as restoring data.')
    print('\n   And the profile names whatever owns the other ~20s, so the')
    print('   plan covers the whole 48.94s rather than the part I measured')
    print('   first.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
