#!/usr/bin/env python3
"""
patch_b5_config_cache.py — stop asking the same questions once per fix.

Ticket B5, part 2 of 2. Apply AFTER patch_b5_io_events.py, and before
measuring: part 1 alone opens the gate, which makes Config_Sources run for
the first time — 4 calls x 2 Cassandra queries x 0.30s is about 2.4s per fix
of work that never happened before, roughly cancelling the 29.6s part 1
removes.

Two changes, both from what the audits measured.

1. THE CONFIG LOOKUP IS CACHED PER REQUEST.
   It depends only on (config_parameter, device_imei) — confirmed from the
   AST: none of the four lookups touches target_io_records. So it has four
   distinct answers per request and was being asked four times per fix.

   Request-scoped, via flask.g, NOT module-level. Config_Sources is called
   from three routes (ComputeTrips_EXCELL, ComputeTrips_PDF, trips_history),
   12 call sites, and the answer is per-device: a module-level dict would
   serve one customer's ignition configuration to another. Outside a request
   context caching is skipped rather than made global.

   It stores the ROW LIST, because callers branch on len(rows) == 1 and both
   0 and 2-or-more must keep falling back.

   A query that RAISED is not cached. cassandra_query returns [] for both "no
   rows" and "the query broke" — same value, different meaning — so caching
   them together would turn one dropped packet into a whole-request fallback
   to speed-derived ignition, with nothing in the output saying so. That is
   why this adds its own call instead of reusing cassandra_query.

2. THE EVENT VALUE COMES FROM DATA ALREADY FETCHED.
   io_events_store.events_for already returns every event for every fix, with
   event_uid and value. Config_Sources' second query asks precisely what is
   in that result. Passed in, it becomes a dict lookup and costs no query:
   four round trips per fix, 1.2s a row and 12s on a ten-row page, become
   zero. The fallback query remains for callers that pass nothing, so the
   excel and pdf routes are untouched until B3.

    python scripts/patch_b5_config_cache.py            # dry run
    python scripts/patch_b5_config_cache.py --apply
"""

import argparse
import difflib
import io
import os
import re
import shutil
import sys
import time

TARGET = os.path.join('endpoints', 'data.py')

CONFIG_CALL = re.compile(
    r"cassandra_query\(\s*\n\s*\"SELECT config_param_data_source_uid[^\"]*\","
    r"\s*\n\s*\('(\w+)',\s*str\(target_device_imei\)\)\s*\n\s*\)")
EVENT_CALL = re.compile(
    r"cassandra_query\(\s*\n\s*\"SELECT event_value_executed[^\"]*\","
    r"\s*\n\s*\(str\((\w+)\),\s*str\(target_io_records\)\)\s*\n\s*\)")

SIGNATURE_OLD = ("def Config_Sources(GetThis, target_device_imei, "
                 "target_io_records, target_actual_speed_x):")
SIGNATURE_NEW = ("def Config_Sources(GetThis, target_device_imei, "
                 "target_io_records, target_actual_speed_x,\n"
                 "                   prefetched_events=None):")

CACHE_HELPER = '''
def _device_config_cache():
    """Per-request store for the device-config lookups.

    Request-scoped on purpose. Config_Sources is called from three routes and
    its answer depends on the device, so a module-level dict would hand one
    customer's ignition configuration to another. Outside a request context —
    a script importing this module — caching is skipped rather than made
    global.
    """
    if not has_request_context():
        return None
    cache = getattr(g, '_navas_device_config_cache', None)
    if cache is None:
        cache = {}
        g._navas_device_config_cache = cache
    return cache

'''

INNER_HELPERS = '''
    def config_source_uid(parameter):
        """The device's configured channel for `parameter`, cached per request.

        The lookup depends only on (parameter, device) — four answers per
        request, where this was asking four times per FIX. Returns the row
        list, because the callers below branch on len(rows) == 1 and both 0
        and 2-or-more must keep falling back.

        A query that raised is NOT cached: cassandra_query cannot tell "no
        rows" from "the query broke", and caching the second would turn one
        dropped packet into a whole-request fallback.
        """
        cache = _device_config_cache()
        key = (parameter, str(target_device_imei))
        if cache is not None and key in cache:
            return cache[key]
        if not session:
            return []
        try:
            rows = list(session.execute(
                "SELECT config_param_data_source_uid FROM "
                "dll_device_local_configs WHERE config_parameter=%s AND "
                "local_device_imei=%s ALLOW FILTERING;",
                (parameter, str(target_device_imei))))
        except Exception:                                   # noqa: BLE001
            return []
        if cache is not None:
            cache[key] = rows
        return rows

    def event_value_for(source_uid):
        """This fix's value for one IO channel.

        When prefetched_events is given — the rows io_events_store already
        fetched for this fix — this is a dict lookup costing no query. At
        0.30s a round trip, four of these per fix was 1.2s a row.

        Returns a one-row list so that the len(rows2) == 1 branches and the
        rows2[0][0] reads below are unchanged.
        """
        wanted = str(source_uid or '').strip()
        if prefetched_events is not None:
            for event in prefetched_events:
                if str(event.get('event_uid') or '').strip() == wanted:
                    return [(event.get('value'),)]
            return []
        if not session:
            return []
        try:
            return list(session.execute(
                "SELECT event_value_executed FROM dll_io_events_executed_logs "
                "WHERE event_uid_executed=%s AND io_parent_io_event_uid=%s "
                "ALLOW FILTERING;", (wanted, str(target_io_records))))
        except Exception:                                   # noqa: BLE001
            return []
'''

SESSION_ANCHOR = "    session = get_cassandra_session()\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    args = ap.parse_args()

    if not os.path.exists(TARGET):
        print(f'!! {TARGET} not found. Run from the repository root.')
        return 1
    raw = io.open(TARGET, encoding='utf-8', newline='').read()
    crlf = raw.count('\r\n') > raw.count('\n') // 2
    src = raw.replace('\r\n', '\n') if crlf else raw
    print(f'line endings : {"CRLF" if crlf else "LF"} (preserved on write)')

    if 'def config_source_uid(' in src:
        print('Already patched. Nothing to do.')
        return 0
    if 'io_events_store.events_for(' not in src:
        print('!! part 1 is not applied. Run patch_b5_io_events.py --apply')
        print('   first: without it Config_Sources still never runs and this')
        print('   change would be unobservable.')
        return 1

    config_hits = CONFIG_CALL.findall(src)
    event_hits = EVENT_CALL.findall(src)
    print(f'config lookups found : {len(config_hits)}  {config_hits}')
    print(f'event lookups found  : {len(event_hits)}  {event_hits}')
    if len(config_hits) != 4 or len(event_hits) != 4:
        print('!! expected exactly 4 of each (ignition, driver, fuel,')
        print('   mileage). Refusing rather than half-patching.')
        return 1

    new = CONFIG_CALL.sub(lambda m: f"config_source_uid('{m.group(1)}')", src)
    new = EVENT_CALL.sub(lambda m: f"event_value_for({m.group(1)})", new)

    if new.count(SIGNATURE_OLD) != 1:
        print(f'!! signature matched {new.count(SIGNATURE_OLD)} time(s)')
        return 1
    new = new.replace(SIGNATURE_OLD, SIGNATURE_NEW, 1)

    if new.count(SESSION_ANCHOR) < 1:
        print('!! could not find "session = get_cassandra_session()" inside '
              'Config_Sources to anchor the helpers')
        return 1
    new = new.replace(SESSION_ANCHOR, SESSION_ANCHOR + INNER_HELPERS, 1)

    # the module-level cache helper, just above Config_Sources
    marker = 'def Config_Sources('
    at = new.index(marker)
    new = new[:at] + CACHE_HELPER.lstrip('\n') + '\n' + new[at:]

    for line in ('from flask import g\n',
                 'from flask import has_request_context\n'):
        if line not in new:
            new = new.replace('from flask import current_app\n',
                              'from flask import current_app\n' + line, 1)

    # trips_history passes the events it already has
    calls = 0
    for kind in ('ignition', 'mileage', 'fuel', 'driver_id'):
        old = (f"Config_Sources('{kind}', DeviceImei, RecordIO_UID, "
               f"int(SPEED))" if kind == 'ignition'
               else f"Config_Sources('{kind}', DeviceImei, RecordIO_UID, "
                    f"SPEED)")
        if old in new:
            new = new.replace(
                old, old[:-1] + ", prefetched_events=_events)", 1)
            calls += 1
    print(f'trips_history call sites given the prefetch: {calls} of 4')
    if calls != 4:
        print('!! expected 4. Refusing.')
        return 1

    try:
        compile(new, TARGET, 'exec')
    except SyntaxError as error:
        print(f'!! does not compile: line {error.lineno}: {error.msg}')
        return 1
    print('the patched file compiles')

    shown = 0
    for line in difflib.unified_diff(src.splitlines(), new.splitlines(),
                                     fromfile='data.py (now)',
                                     tofile='data.py (patched)',
                                     lineterm='', n=1):
        print(line)
        shown += 1
        if shown > 150:
            print('   ... diff truncated')
            break

    if not args.apply:
        print('\n--- DRY RUN. Nothing written. ---')
        print('    python scripts/patch_b5_config_cache.py --apply')
        return 0

    backup = f'{TARGET}.bak.{time.strftime("%Y%m%d-%H%M%S")}'
    shutil.copy2(TARGET, backup)
    io.open(TARGET, 'w', encoding='utf-8', newline='').write(
        new.replace('\n', '\r\n') if crlf else new)
    print(f'\nwritten. backup at {backup}')
    print('\nThen measure:')
    print('  python scripts/b5_measure.py')
    return 0


if __name__ == '__main__':
    sys.exit(main())
