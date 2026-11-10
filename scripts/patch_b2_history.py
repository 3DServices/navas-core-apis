#!/usr/bin/env python3
"""
patch_b2_history.py — switch /data-stream/trips/history onto location_store.

Ticket B2. ONE route, deliberately: trips/excel, trips/pdf and
trips/history/replay read positions the same way and are B3. Switching all four
at once means a parity failure takes down reports, exports and replay together,
and leaves nothing working to compare against.

THIS SCRIPT REFUSES TO WRITE UNTIL B1 HAS PASSED.
Run it with no flags to see the diff and have the result compiled without
anything being written:

    python scripts/patch_b2_history.py

Then, only after location_store_parity.py reports MATCH:

    python scripts/patch_b2_history.py --apply --b1-passed

The --b1-passed flag is not ceremony. The new reader orders by
record_timestamp instead of data_idx and dedupes in Python instead of in SQL.
If those two choices are wrong, trip history starts lying rather than failing,
and nobody notices for a month. Parity against a window where both stores hold
data is the only evidence that they are right.

What changes, and why each change is necessary
----------------------------------------------
1. The position SELECT becomes location_store.fixes(). Same unit, same date
   window, same limit/offset, read from Cassandra, which is where positions
   have actually been written since 06-08-2025.

2. PositionsUnavailable returns 503, not 'No Trips Found'. A store that cannot
   be read is not a vehicle that did not move. This is the same distinction
   FleetUnavailable exists to protect, and the reason Waswa once told a
   customer with five vehicles that they owned none.

3. The outer `elif(cursor.rowcount == 0)` becomes a plain `else`. This one is
   easy to miss and would be a live bug: once the position query is gone,
   cursor.rowcount belongs to the LAST IO-event query inside the loop, so
   using it as the gate for "were there any trips" would report whatever the
   final IO lookup happened to return.

The cursor block itself stays. The IO-event, vendor and config lookups inside
the loop are still Postgres reads and still need it.

Verified before this script was written
---------------------------------------
All five history-shaped call sites consume trip[0] through trip[10] only.
as_history_tuple is 12 wide, so index 11 (row_index) is selected by the old
SQL and never read. The contract holds with room to spare.
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
FUNC = 'trips_history'

OLD_READ = """                                cursor.execute("SELECT data_longitude, data_latitude, speed_log, data_hdop, local_system_datestamp, record_io_events_uid, geocoded_location, local_system_timestamp, data_connected_satelites, batch_uid, data_idx, ROW_NUMBER() OVER (ORDER BY data_idx DESC) AS row_index FROM (SELECT *, ROW_NUMBER() OVER (PARTITION BY data_longitude, data_latitude ORDER BY data_idx DESC) AS row_num FROM dll_location_registry WHERE data_device_imei = %s AND TO_DATE(local_system_datestamp, 'DD-MM-YYYY') BETWEEN TO_DATE(%s, 'DD-MM-YYYY') AND TO_DATE(%s, 'DD-MM-YYYY')) AS subquery WHERE row_num = 1 ORDER BY data_idx DESC LIMIT %s OFFSET %s;", (DeviceImei, FromDate, ToDate, Record_Count, Offset_Record,))

                                if(cursor.rowcount >= 1):

                                    trips_data_adapter = cursor.fetchall()
"""

NEW_READ = """                                try:
                                    _fixes, _truncated = location_store.fixes(
                                        get_cassandra_session(), DeviceImei,
                                        FromDate, ToDate,
                                        limit=Record_Count,
                                        offset=Offset_Record)
                                except location_store.PositionsUnavailable as _error:
                                    # "We could not look" must never render as
                                    # "this vehicle did not move."
                                    logging.warning(
                                        "trips_history: position store unavailable "
                                        "for %s (%s to %s): %s",
                                        DeviceImei, FromDate, ToDate, _error)
                                    return reply('error', 503, 'Position data is temporarily unavailable, please retry', '')

                                if _fixes:

                                    trips_data_adapter = [location_store.as_history_tuple(_row) for _row in _fixes]
"""

OLD_GATE = """                                elif(cursor.rowcount == 0):
                                    return reply('error', 400, 'No Trips Found', '')
                                else:
                                    return reply('error', 400, 'Unable to complete request', '')
"""

NEW_GATE = """                                else:
                                    # Not cursor.rowcount: it now belongs to the
                                    # IO-event queries inside the loop above, so
                                    # it can no longer answer "were there trips".
                                    return reply('error', 400, 'No Trips Found', '')
"""

IMPORT_ANCHOR = "from .globals import CheckHardware2\n"
IMPORT_LINE = "from . import location_store\n"


def func_span(src, name):
    """Line offsets of one top-level function, so an edit cannot stray into a
    sibling route that contains the identical text."""
    lines = src.splitlines(keepends=True)
    start = None
    for i, line in enumerate(lines):
        if re.match(rf'def {name}\(', line):
            start = i
            break
    if start is None:
        return None
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if re.match(r'def \w+\(|@\w+\.route\(', lines[j]):
            end = j
            break
    head = ''.join(lines[:start])
    body = ''.join(lines[start:end])
    tail = ''.join(lines[end:])
    return head, body, tail


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true',
                    help='write the change (requires --b1-passed)')
    ap.add_argument('--b1-passed', action='store_true',
                    help='location_store_parity.py reported MATCH')
    args = ap.parse_args()

    if not os.path.exists(TARGET):
        print(f'!! {TARGET} not found. Run from the repository root.')
        return 1

    raw = io.open(TARGET, encoding='utf-8', newline='').read()

    # data.py is CRLF. Matching and editing happen on LF text, and the file is
    # written back in its own convention — otherwise a four-line change lands
    # as a 2,716-line diff and nobody can review it.
    crlf = raw.count('\r\n') > raw.count('\n') // 2
    src = raw.replace('\r\n', '\n') if crlf else raw
    print(f'line endings : {"CRLF" if crlf else "LF"} (preserved on write)')

    if 'location_store.fixes(' in src:
        print('Already patched: data.py calls location_store.fixes().')
        print('Nothing to do.')
        return 0

    split = func_span(src, FUNC)
    if split is None:
        print(f'!! could not locate def {FUNC}( in {TARGET}')
        return 1
    head, body, tail = split

    problems = []
    if body.count(OLD_READ) != 1:
        problems.append(f'the position read matched {body.count(OLD_READ)} '
                        f'time(s) inside {FUNC}(), expected exactly 1')
    if body.count(OLD_GATE) != 1:
        problems.append(f'the rowcount gate matched {body.count(OLD_GATE)} '
                        f'time(s) inside {FUNC}(), expected exactly 1')
    if problems:
        print('!! refusing to patch — the file is not in the shape this script')
        print('   was written against:')
        for p in problems:
            print(f'     - {p}')
        print('\n   Re-read the route and update this script rather than')
        print('   loosening the match. A patch that silently edits nothing is')
        print('   worse than one that fails.')
        return 1

    new_body = body.replace(OLD_READ, NEW_READ).replace(OLD_GATE, NEW_GATE)
    new_src = head + new_body + tail

    if IMPORT_LINE not in new_src:
        if IMPORT_ANCHOR not in new_src:
            print(f'!! import anchor not found: {IMPORT_ANCHOR.strip()}')
            return 1
        new_src = new_src.replace(IMPORT_ANCHOR,
                                  IMPORT_ANCHOR + IMPORT_LINE, 1)

    # Compile before anything is written. A patch that produces a file Python
    # cannot parse takes the whole API down on restart.
    try:
        compile(new_src, TARGET, 'exec')
    except SyntaxError as error:
        print(f'!! the patched file does not compile: line {error.lineno}: '
              f'{error.msg}')
        print('   Nothing was written.')
        return 1
    print('the patched file compiles')

    changed = sum(1 for line in difflib.unified_diff(
        src.splitlines(), new_src.splitlines(), n=0) if line[:1] in '+-')
    print(f'{changed} line(s) differ\n')
    for line in difflib.unified_diff(src.splitlines(), new_src.splitlines(),
                                     fromfile='data.py (now)',
                                     tofile='data.py (patched)',
                                     lineterm='', n=3):
        print(line)

    if not args.apply:
        print('\n--- DRY RUN. Nothing was written. ---')
        print('After location_store_parity.py reports MATCH:')
        print('    python scripts/patch_b2_history.py --apply --b1-passed')
        return 0

    if not args.b1_passed:
        print('\n!! --apply requires --b1-passed.')
        print('   The new reader orders by record_timestamp and dedupes in')
        print('   Python. Until parity confirms those match the old query on')
        print('   data both stores hold, switching the route would replace a')
        print('   visible failure with a silent wrong answer.')
        print('\n   Run this first:')
        print('     python scripts/location_store_parity.py --imei 867556044727322 \\')
        print('         --from 15-07-2025 --to 01-08-2025')
        return 1

    backup = f'{TARGET}.bak.{time.strftime("%Y%m%d-%H%M%S")}'
    shutil.copy2(TARGET, backup)
    out = new_src.replace('\n', '\r\n') if crlf else new_src
    io.open(TARGET, 'w', encoding='utf-8', newline='').write(out)
    print(f'\nwritten. backup at {backup}')
    print('\nNext:')
    print('  1. restart Flask')
    print('  2. POST /data-stream/trips/history for a unit and a RECENT date')
    print('     range — the case that returned nothing before')
    print('  3. POST the same for a July 2025 range and compare against the')
    print('     numbers location_store_parity.py printed')
    print('  4. B3 switches trips/excel, trips/pdf and trips/history/replay')
    return 0


if __name__ == '__main__':
    sys.exit(main())
