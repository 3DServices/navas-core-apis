#!/usr/bin/env python3
"""The probe gave up when Cassandra did. It shouldn't have.

    Error connecting to Cassandra: ('Unable to connect to any servers', ...)
    Nothing to probe. Pass --client or --imei.

A client WAS passed. The probe needed Cassandra only to turn that client into a
list of IMEIs, then swallowed the failure and reported it as a missing argument
— which is both wrong and the same sin the assistant was committing: a failure
to read, described as an absence.

Worse, the two questions that run entirely on Postgres — is the position
pipeline alive for anyone, and does dll_trips_auditor hold trips — need no
IMEIs at all, and were skipped for want of a Cassandra connection they never
required.

After this: a Cassandra outage is reported as an outage, the Postgres checks
run regardless, and the IMEIs from the last good run are offered so the
per-unit checks can still be done by hand.

Idempotent.
"""
import ast
import io
import sys

PATH = 'scripts/waswa_data_probe.py'

OLD = """    imeis = list(args.imei or [])
    if args.client:
        from flask import Flask
        app = Flask(__name__)
        app.config['db_link'] = DB_LINK
        with app.app_context():
            scope = waswa_fleet.build_scope('PROBE', args.client, is_staff=True)
            fleet = waswa_fleet.unit_find(scope=scope)
        for u in (fleet.get('units') or []):
            if u.get('imei') and u['imei'] not in imeis:
                imeis.append(u['imei'])

    if not imeis:
        print('Nothing to probe. Pass --client or --imei.')
        return 1

    print(f'probing {len(imeis)} unit(s) at {datetime.now():%Y-%m-%d %H:%M}')
    conn = psycopg2.connect(DB_LINK)
    try:
        with conn.cursor() as cur:
            probe_positions(cur, imeis)
            probe_table_recency(cur)
            probe_trips(cur, imeis)
    finally:
        conn.close()

    probe_heartbeats(imeis)
    print('\\nDone.')
    return 0"""

NEW = """    imeis = list(args.imei or [])
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
        print('\\n!! The vehicle register (Cassandra dll_device_basic_data) could')
        print(f'   not be read: {str(register_down)[:120]}')
        print('   The per-unit checks below need it; the table-wide ones do not.')
        if not imeis:
            print('   To check specific units anyway, pass them directly, e.g.')
            print('     --imei 862846042593213 --imei 867556044727322')

    print(f'\\nprobing {len(imeis)} unit(s) at {datetime.now():%Y-%m-%d %H:%M}')
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

    print('\\nDone.')
    return 2 if register_down and not imeis else 0"""


def main():
    src = io.open(PATH, encoding='utf-8', newline='').read()
    if 'register_down' in src:
        print('  already resilient')
        return 0
    if OLD not in src:
        print('  !! main() not found verbatim — stopping, nothing written')
        return 1
    out = src.replace(OLD, NEW, 1)
    ast.parse(out)
    io.open(PATH, 'w', encoding='utf-8', newline='').write(out)
    print('  Postgres checks now run even when Cassandra is down')
    print('  an outage is reported as an outage, not as a missing argument')
    print(f'  written: {PATH}')
    print('  syntax OK')
    return 0


if __name__ == '__main__':
    sys.exit(main())
