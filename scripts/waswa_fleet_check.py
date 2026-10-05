#!/usr/bin/env python3
"""
waswa_fleet_check.py — run Waswa's fleet tools directly, with no model involved.

Why this exists: waswa_fleet.py has unit tests, but they cover arithmetic and
scoping, not SQL. Every query in it was written from the shapes in data.py and
statistics.py and none had been run. A wrong column name, a date format that
does not match how dll_location_registry stores its text, a Cassandra table
that is named something else in this environment — all of those look identical
from the chat window: Waswa says it could not find anything.

This calls each tool the way assistant.py would and prints exactly what comes
back, so a failure names its own cause.

The Places probe is OFF by default and costs money when you turn it on — one
billed request per sampled point, up to the cap. Run it once, deliberately.

Usage:
    python scripts/waswa_fleet_check.py --client CLIENT_UID
    python scripts/waswa_fleet_check.py --client CLIENT_UID --imei 86xxxxxxxxxxxxx
    python scripts/waswa_fleet_check.py --client CLIENT_UID --days 3
    python scripts/waswa_fleet_check.py --client CLIENT_UID --probe --place-type mosque --min-speed 60
"""

import argparse
import json
import sys
from datetime import datetime, timedelta

from flask import Flask

sys.path.insert(0, '.')
from config import DB_LINK                      # noqa: E402
from endpoints import waswa_fleet               # noqa: E402

DATE_FMT = '%d-%m-%Y'


def show(title, result, limit=1400):
    print(f'\n── {title} ' + '─' * max(0, 70 - len(title)))
    if result is None:
        print('   None  (this tool name is not owned by waswa_fleet)')
        return
    text = json.dumps(result, indent=2, default=str)
    print(text if len(text) <= limit else text[:limit] + '\n   … truncated')


def verdict(result, what):
    """One line a person can act on."""
    if not isinstance(result, dict):
        return f'   ?? {what}: unexpected result type {type(result).__name__}'
    if 'error' in result:
        return f'   !! {what} RAISED: {result["error"]}'
    if result.get('found'):
        return f'   OK {what}'
    return f'   -- {what}: found=false — {result.get("reason") or "no reason given"}'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--client', required=True,
                    help='client_uid whose fleet to read (account_root)')
    ap.add_argument('--imei', help='unit to inspect; default: the first found')
    ap.add_argument('--days', type=int, default=2,
                    help='how far back to look for trips (default 2)')
    ap.add_argument('--probe', action='store_true',
                    help='ALSO run the Places probe — this costs money')
    ap.add_argument('--place-type', default='mosque')
    ap.add_argument('--min-speed', type=float, default=60.0)
    args = ap.parse_args()

    app = Flask(__name__)
    app.config['db_link'] = DB_LINK

    with app.app_context():
        # Staff scope, so --client is honoured. A customer's scope would pin to
        # their own client and ignore it — which is the point of the scoping
        # test, not of this script.
        scope = waswa_fleet.build_scope('CHECK-SCRIPT', args.client, is_staff=True)
        print(f'client   : {args.client}')
        print(f'scope    : {scope}')

        # 1. Can we see the fleet at all? Everything else depends on this.
        fleet = waswa_fleet.unit_find(scope=scope)
        show('unit_find (list the fleet)', fleet)
        print(verdict(fleet, 'unit_find'))
        if not fleet.get('found'):
            print('\n   Nothing else can work until this does. Check, in order:')
            print('     * is Cassandra reachable from this process?')
            print('     * does dll_device_basic_data.device_client hold this uid?')
            print('     * is the uid the CLIENT (account_root), not a login?')
            return 1

        units = fleet.get('units') or []
        imei = args.imei or (units[0]['imei'] if units else None)
        if not imei:
            print('\n   The fleet listed no units with an IMEI.')
            return 1
        print(f'\nunit     : {imei}')

        # 2. Name matching — the tool that makes "which vehicle?" possible.
        name = (units[0].get('name') or '').strip()
        if name:
            found = waswa_fleet.unit_find(query=name, scope=scope)
            show(f'unit_find (by name {name!r})', found)
            print(verdict(found, 'unit_find by name'))

        # 3. The offline-diagnosis tool.
        status = waswa_fleet.unit_status(imei=imei, scope=scope)
        show('unit_status', status)
        print(verdict(status, 'unit_status'))
        if isinstance(status, dict):
            if status.get('last_reported_at') is None and status.get('found'):
                print('   note: no heartbeat row — check dll_pulse_status_registry')
            if status.get('paused_by_rule') == 'pause rules could not be read':
                print('   note: dll_pause_rules query failed — check its columns')

        # 4. The position query. This is the one most likely to be wrong.
        to_date = datetime.now()
        from_date = to_date - timedelta(days=max(1, args.days))
        trips = waswa_fleet.unit_trips(
            imei=imei,
            from_date=from_date.strftime(DATE_FMT),
            to_date=to_date.strftime(DATE_FMT),
            scope=scope)
        show('unit_trips', trips)
        print(verdict(trips, 'unit_trips'))
        if isinstance(trips, dict) and not trips.get('found'):
            print('   Trips now come from Postgres dll_trips_auditor, the same')
            print('   table the console Trips report reads. If the console shows')
            print('   trips for this unit and Waswa does not, the fault is here;')
            print('   if neither does, the unit genuinely has none recorded.')
            print(f"     * try:  SELECT COUNT(*), MAX(trip_date) FROM"
                  f" dll_trips_auditor WHERE device_imei = '{imei}';")

        # 5. Scoping — the check that matters most. A customer must not be able
        #    to read this fleet by naming it.
        outsider = waswa_fleet.build_scope('SOME-CUSTOMER', 'NOT-THIS-CLIENT',
                                           is_staff=False)
        leak = waswa_fleet.dispatch('unit_status',
                                    {'imei': imei, 'client_uid': args.client},
                                    scope=outsider)
        show('scoping: a customer naming this client', leak)
        if isinstance(leak, dict) and leak.get('found'):
            print('   !! LEAK — a customer read another client\'s unit. Stop and fix.')
            return 2
        print('   OK refused, as it must be')

        # 6. The fleet roll-up.
        activity = waswa_fleet.fleet_activity(days=max(1, args.days), scope=scope)
        show('fleet_activity', activity)
        print(verdict(activity, 'fleet_activity'))

        # 7. Places — only when asked for, because it bills per request.
        if args.probe:
            print(f'\n   Probing for {args.place_type!r} above {args.min_speed} km/h.')
            print(f'   Up to {waswa_fleet._MAX_PROBES} billed Places requests.')
            probe = waswa_fleet.unit_route_probe(
                imei=imei,
                from_date=from_date.strftime(DATE_FMT),
                to_date=to_date.strftime(DATE_FMT),
                place_type=args.place_type,
                min_speed=args.min_speed,
                scope=scope)
            show('unit_route_probe', probe)
            print(verdict(probe, 'unit_route_probe'))
            if isinstance(probe, dict):
                print(f'   billed requests: {probe.get("places_checked", 0)}')
                if 'not configured' in str(probe.get('reason') or ''):
                    print('   set GOOGLE_MAPS_API_KEY and enable the Places API')
        else:
            print('\n── unit_route_probe ' + '─' * 52)
            print('   skipped — pass --probe to run it (costs money)')

    print('\nDone.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
