#!/usr/bin/env python3
"""
waswa_parity_check.py — does Waswa read what the apps read?

Waswa does not call the HTTP API. It queries Postgres and Cassandra directly,
which is faster and avoids a round trip, and carries one risk the API does not:
if Waswa reads a different table from the endpoint that serves the same screen,
the customer gets two different answers to the same question and believes
neither. Scoping is not the worry — that is tested elsewhere — the worry is
SOURCE DRIFT.

So this runs the SERVING endpoint's own query, verbatim from its source file,
next to Waswa's tool, and compares the numbers.

  unit list   devices.py:306      Cassandra dll_device_basic_data (device_client)
              waswa_fleet._units_of   same table, same predicate
  balance     tokens_billing.ClientToken_Balance
                                  dll_user_token_accounts, client_uid = ANY(owners)
              waswa_context._token_position   same, same resolver
  heartbeat   statistics.py:723   Cassandra dll_pulse_status_registry
              waswa_fleet.unit_status         same query
  trips       data.py:2271        dll_trips_auditor, trip_status='ended'
              waswa_fleet.unit_trips         same table
  positions   data.py:630         POSTGRES dll_location_registry
              waswa_fleet._points            CASSANDRA ..._by_record_ts

That last pair is a known divergence, not a bug in Waswa: the Postgres copy
stopped taking rows on 06-08-2025 while the device listener kept writing to
Cassandra. Waswa is reading the live store and the API is reading a dead one, so
they disagree and Waswa is the one that is right. It is reported loudly because
the fix belongs in data.py, not here.

Read-only.

Usage:
    python scripts/waswa_parity_check.py --client CLIENT_UID
    python scripts/waswa_parity_check.py --client CLIENT_UID --imei 350317173603857
"""

import argparse
import sys
from datetime import datetime, timedelta

import psycopg2

sys.path.insert(0, '.')
from config import DB_LINK                             # noqa: E402
from endpoints import waswa_fleet                      # noqa: E402
from endpoints.globals import resolve_wallet_owner     # noqa: E402

DATE_FMT = '%d-%m-%Y'
RESULTS = []


def verdict(label, served, waswa, note=None, expect_differ=False):
    same = served == waswa
    if expect_differ:
        mark = 'DIVERGES (expected)' if not same else 'MATCH (unexpected)'
    else:
        mark = 'MATCH' if same else '!! DIFFERS'
    RESULTS.append((mark, label))
    print(f'\n   {label}')
    print(f'      endpoint : {served}')
    print(f'      Waswa    : {waswa}')
    print(f'      -> {mark}')
    if note:
        print(f'      {note}')


def check_units(session, cur, client):
    """devices.py lists a client's devices with exactly this CQL."""
    stmt = session.prepare(
        "SELECT device_imei FROM dll_device_basic_data "
        "WHERE device_client = ? ALLOW FILTERING")
    served = len(list(session.execute(stmt, (str(client),))))

    scope = waswa_fleet.build_scope('PARITY', client, is_staff=True)
    found = waswa_fleet.unit_find(scope=scope)
    mine = found.get('count') if found.get('found') else 0
    verdict('unit count (dll_device_basic_data, device_client)', served, mine,
            'same table and same predicate as devices.py:306')
    return [u['imei'] for u in (found.get('units') or []) if u.get('imei')]


def check_balance(cur, client):
    """ClientToken_Balance sums these two columns over the wallet family."""
    _, owners = resolve_wallet_owner(cur, client)
    cur.execute(
        "SELECT COALESCE(SUM(CASE WHEN token_units_left ~ '^[0-9]+(\\.[0-9]+)?$' "
        "                        THEN token_units_left::numeric ELSE 0 END), 0) "
        "FROM dll_user_token_accounts WHERE client_uid = ANY(%s)", (owners,))
    served = float(cur.fetchone()[0] or 0)

    from endpoints.waswa_context import _token_position
    position, reason = _token_position(cur, client)
    # Waswa omits token_units_left entirely when no pack held a parseable
    # number, rather than reporting 0 as if it had measured one. That is the
    # honest state, so say it rather than printing the whole dict.
    mine = None
    if isinstance(position, dict):
        if 'token_units_left' in position:
            mine = position['token_units_left']
        else:
            mine = ('not reported — no pack held a parseable value '
                    f"(packs={position.get('token_packs')}, "
                    f"statuses={position.get('pack_statuses')})")
            if served == 0:
                mine += '  [agrees with the endpoint summing to 0]'
    verdict('token units left (dll_user_token_accounts, ANY(owners))',
            served, mine,
            f'both call resolve_wallet_owner; owners={len(owners)}'
            + (f'; reason={reason}' if reason else ''))


def check_heartbeat(session, imei):
    """statistics.py:723 and waswa_fleet use the identical CQL."""
    stmt = session.prepare(
        "SELECT last_heartbeat_date, last_heartbeat_time "
        "FROM dll_pulse_status_registry WHERE device_data_imei = ? LIMIT 1")
    row = session.execute(stmt, (str(imei),)).one()
    served = (f'{row.last_heartbeat_date} {row.last_heartbeat_time}'
              if row else '(no row)')

    scope = waswa_fleet.build_scope('PARITY', None, is_staff=True)
    status = waswa_fleet.unit_status(imei=imei, scope=scope)
    mine = status.get('last_reported_at') or '(none)'
    # The endpoint returns raw text, Waswa a parsed timestamp — compare the
    # instant they describe, not the spelling.
    parsed = waswa_fleet._stamp(
        getattr(row, 'last_heartbeat_date', None),
        getattr(row, 'last_heartbeat_time', None)) if row else None
    verdict('last heartbeat (dll_pulse_status_registry)',
            parsed.isoformat(sep=' ') if parsed else '(none)', mine,
            f'endpoint stores it as text: {served!r}')


def check_trips(cur, imei, days):
    """data.py:2271 — the Trips report's own query."""
    end = datetime.now().date()
    start = end - timedelta(days=days)
    cur.execute("""
        SELECT COUNT(*) FROM dll_trips_auditor
         WHERE trip_date BETWEEN %s AND %s
           AND device_imei = %s AND trip_status = %s""",
                (start, end, str(imei), 'ended'))
    served = cur.fetchone()[0]

    scope = waswa_fleet.build_scope('PARITY', None, is_staff=True)
    mine_result = waswa_fleet.unit_trips(
        imei=imei, from_date=start.strftime(DATE_FMT),
        to_date=end.strftime(DATE_FMT), scope=scope)
    trips = mine_result.get('trips') or []
    mine = sum(1 for t in trips if not t.get('in_progress'))
    total = mine_result.get('trip_count')
    verdict(f'ended trips, {start} to {end} (dll_trips_auditor)', served, mine,
            f'Waswa also counts {total - mine if total else 0} in progress; '
            f'the report filters trip_status=ended only')


def check_positions(cur, imei, days):
    """The known divergence. Reported, not hidden."""
    end = datetime.now().date()
    start = end - timedelta(days=days)
    cur.execute("""
        SELECT COUNT(*) FROM dll_location_registry
         WHERE data_device_imei = %s
           AND TO_DATE(local_system_datestamp, 'DD-MM-YYYY')
               BETWEEN TO_DATE(%s, 'DD-MM-YYYY') AND TO_DATE(%s, 'DD-MM-YYYY')""",
                (str(imei), start.strftime(DATE_FMT), end.strftime(DATE_FMT)))
    served = cur.fetchone()[0]
    mine = len(waswa_fleet._points(imei, start.strftime(DATE_FMT),
                                   end.strftime(DATE_FMT)))
    verdict('position fixes in the window', served, mine,
            'endpoint: POSTGRES dll_location_registry (last row 06-08-2025). '
            'Waswa: CASSANDRA dll_location_registry_by_record_ts (live). '
            'Fix belongs in data.py — Waswa is reading the correct store.',
            expect_differ=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--client', required=True)
    ap.add_argument('--imei', help='default: the first unit on the client')
    ap.add_argument('--days', type=int, default=7)
    args = ap.parse_args()

    from flask import Flask
    app = Flask(__name__)
    app.config['db_link'] = DB_LINK

    conn = psycopg2.connect(DB_LINK)
    try:
        with app.app_context(), conn.cursor() as cur:
            session = waswa_fleet._cassandra()
            print(f'client : {args.client}')
            print('Comparing each serving endpoint\'s own query with Waswa\'s tool.')

            imeis = check_units(session, cur, args.client)
            check_balance(cur, args.client)

            imei = args.imei or (imeis[0] if imeis else None)
            if not imei:
                print('\n   No unit to inspect; skipping the per-unit checks.')
            else:
                print(f'\n   unit under test: {imei}')
                check_heartbeat(session, imei)
                check_trips(cur, imei, args.days)
                check_positions(cur, imei, args.days)
    finally:
        conn.close()

    print('\n== Summary ' + '=' * 64)
    for mark, label in RESULTS:
        print(f'   {mark:<22} {label}')
    bad = [r for r in RESULTS if r[0].startswith('!!')]
    print()
    if bad:
        print(f'   {len(bad)} source(s) disagree in a way that is NOT expected.')
        print('   A customer asking the same question twice would get two')
        print('   answers. Fix before anything else.')
        return 1
    print('   Every source Waswa reads is the one the app reads, except the')
    print('   position store, where the app is the one that is stale.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
