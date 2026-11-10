#!/usr/bin/env python3
"""
B4 -- add POST /data-stream/trips/stops to endpoints/data.py.

Option C of the three the audit surfaced: trips/history keeps its fix
pagination exactly as B2 left it, and stop detection gets its own path which
reads its window unpaginated and paginates STOPS.

Why not inside trips/history: that route paginates fixes, and a stop is an
aggregation over contiguous fixes -- arrival is the first of a run, departure
the last -- so a page boundary splits a run and the same stop reports a
different dwell on page 1 and page 2.  See endpoints/stops.py.

Two edits:
  1. `from . import stops` beside the existing store imports
  2. the route appended at end of file, with STOPS_MAX_DAYS above it

The route is protected by default: endpoints/access_guard.py treats
PUBLIC_RULES as an allowlist, so an unlisted rule requires a token and the
IMEI check, exactly like trips/history.  No rule entry is needed, and adding
one would have *reduced* protection.

Dry run by default.  Pass --apply to write.
"""

import argparse
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TARGET = os.path.join(ROOT, 'endpoints', 'data.py')

IMPORT_ANCHOR = 'from . import io_events_store\n'
IMPORT_NEW = 'from . import io_events_store\nfrom . import stops\n'

ROUTE = '''

# ──────────────────────────────────────────────────────────────────────────────
# B4 — STOPS
#
# A stop is an aggregation over CONTIGUOUS fixes, so it cannot be derived from
# a paginated slice of them: a page boundary cuts a run in half and gives its
# edges a dwell that differs between pages.  trips/history paginates fixes, so
# stops live here instead, reading their window unpaginated and paginating the
# stops themselves.  Detection logic is in endpoints/stops.py (pure, tested).
# ──────────────────────────────────────────────────────────────────────────────

# Tighter than trips/history's 92-day span, because this path cannot stop
# reading early.  The busiest unit writes ~13,400 fixes a day, so 31 days is
# ~415,000 — already at location_store.MAX_ROWS.  Rejecting a longer range with
# a clear 400 beats letting MAX_ROWS raise and answering 503, which would tell
# the caller to retry something that can never succeed.
STOPS_MAX_DAYS = 31


#derive stops (arrival, departure, dwell) from the live position store
@data_stream.route("/data-stream/trips/stops", methods=["POST"])
def trips_stops():

    try:

        payload_data = request.get_json(silent=True) or {}
        request_data = payload_data.get('data') or {}

        DeviceImei = str(request_data.get('device_imei') or '').strip()
        FromDate = str(request_data.get('from_date') or '').strip()
        ToDate = str(request_data.get('to_date') or '').strip()

        if (len(DeviceImei) < 5) or (len(FromDate) < 5) or (len(ToDate) < 5):
            return reply('error', 400,
                         'device_imei, from_date and to_date are required', '')

        # days_in() is location_store's own parser, so the date formats this
        # route accepts cannot drift from the ones the read accepts.
        TheDays, RangeTruncated = location_store.days_in(FromDate, ToDate)

        if not TheDays:
            return reply('error', 400,
                         'from_date and to_date did not parse as dates', '')

        if len(TheDays) > STOPS_MAX_DAYS:
            return reply('error', 400,
                         'Stops can be derived for at most %d days at a time; '
                         'this request spans %d days'
                         % (STOPS_MAX_DAYS, len(TheDays)), '')

        DetectionSettings = {}

        for FieldName, Caster in (('stationary_speed', float),
                                  ('min_dwell_seconds', int),
                                  ('max_gap_seconds', int)):
            if request_data.get(FieldName) is not None:
                try:
                    DetectionSettings[FieldName] = Caster(request_data[FieldName])
                except (TypeError, ValueError):
                    return reply('error', 400,
                                 '%s must be a number' % FieldName, '')

        device_billing_check = check_device(DeviceImei)

        if(device_billing_check != 'running'):
            return reply('error', 403,
                         'This device is not currently running', '')

        # dedupe_coordinates=False is essential, not an option: the dedupe
        # keeps one fix per (lon, lat) — the latest — which discards the
        # arrival time, the very quantity being measured.
        #
        # limit=None takes the full-read path, guarded by MAX_ROWS.  The day
        # cap above means that guard should not fire.
        try:
            TheFixes, FixesTruncated = location_store.fixes(
                get_cassandra_session(), DeviceImei, FromDate, ToDate,
                dedupe_coordinates=False, limit=None, newest_first=False)
        except location_store.PositionsUnavailable as error:
            logging.warning('trips_stops: position store unavailable: %s', error)
            return reply('error', 503,
                         'Position data is temporarily unavailable, please retry',
                         '')

        StopsResult = stops.detect(TheFixes, **DetectionSettings)

        StopsFound = StopsResult['stops']
        StopsTotal = len(StopsFound)

        # Pagination applies to STOPS, not to fixes.
        try:
            Offset_Record = max(0, int(request_data.get('offset_log') or 0))
        except (TypeError, ValueError):
            Offset_Record = 0

        try:
            Record_Count = int(request_data.get('record_count') or 0)
        except (TypeError, ValueError):
            Record_Count = 0

        if Record_Count > 0:
            StopsResult['stops'] = StopsFound[
                Offset_Record:Offset_Record + Record_Count]
        else:
            StopsResult['stops'] = StopsFound[Offset_Record:]

        StopsResult['stops_total'] = StopsTotal
        StopsResult['offset_log'] = Offset_Record
        StopsResult['record_count'] = Record_Count
        StopsResult['days_requested'] = len(TheDays)
        StopsResult['range_truncated'] = bool(RangeTruncated or FixesTruncated)

        if StopsTotal == 0:
            # 400 with the body kept, matching 'No Trips Found' in this file.
            # The body still carries fix_count and speed_trustworthy, so a
            # caller can tell "it never stopped" from "we could not tell".
            return reply('error', 400, 'No Stops Found', StopsResult)

        return reply('success', 200, 'Stops Found', StopsResult)

    except Exception as error:
        logging.exception('trips_stops failed')
        return reply('error', 500, str(error), '')
'''


def read_source(path):
    with io.open(path, 'rb') as handle:
        text = handle.read().decode('utf-8')
    return text.replace('\r\n', '\n'), ('\r\n' in text)


def write_source(path, text, crlf):
    out = text.replace('\n', '\r\n') if crlf else text
    with io.open(path, 'wb') as handle:
        handle.write(out.encode('utf-8'))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()

    text, crlf = read_source(TARGET)
    before = text.count('\n') + 1

    if 'def trips_stops(' in text:
        print('SKIP: trips_stops() already present.')
        return 0

    if text.count(IMPORT_ANCHOR) != 1:
        print('FAIL: expected exactly 1 import anchor, found %d'
              % text.count(IMPORT_ANCHOR))
        return 1
    text = text.replace(IMPORT_ANCHOR, IMPORT_NEW, 1)

    text = text.rstrip('\n') + '\n' + ROUTE

    try:
        compile(text, TARGET, 'exec')
    except SyntaxError as error:
        print('FAIL: patched source does not compile: %s' % error)
        return 1

    # the route must be the only new module-level def
    import ast
    names_before = set()
    for node in ast.parse(read_source(TARGET)[0]).body:
        if isinstance(node, ast.FunctionDef):
            names_before.add(node.name)
    names_after = set()
    for node in ast.parse(text).body:
        if isinstance(node, ast.FunctionDef):
            names_after.add(node.name)
    added = names_after - names_before
    if added != {'trips_stops'}:
        print('FAIL: expected to add only trips_stops(), added %s' % (added or 'nothing'))
        return 1

    print('endpoints/data.py  %s  %d -> %d lines'
          % ('CRLF' if crlf else 'LF', before, text.count('\n') + 1))
    print('  * added `from . import stops`')
    print('  * appended trips_stops() + STOPS_MAX_DAYS')
    print('  * module-level defs added: %s' % ', '.join(sorted(added)))

    if not args.apply:
        print('\nDRY RUN -- nothing written.  Re-run with --apply.')
        return 0

    write_source(TARGET, text, crlf)
    print('\nWRITTEN.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
