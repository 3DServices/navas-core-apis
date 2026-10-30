#!/usr/bin/env python3
"""
patch_b5_io_events.py — trips_history reads IO events from the live store.

Ticket B5, part 1 of 2. Part 2 is the request-scoped config cache.

What the audits established, none of it assumed
-----------------------------------------------
* Postgres dll_io_events_executed_logs holds 55M rows in 11 GB with no index
  on io_parent_io_event_uid, and contains NONE of these uids: 0 of 10 recent,
  0 of 3 old. Each lookup was a parallel seq scan discarding ~19.7M rows per
  worker, 2.9s, to return nothing. Ten of them were 29.6s of the measured
  48.94s.
* Cassandra holds the same table with io_parent_io_event_uid as the PARTITION
  KEY — a point read, 0.30s, flat over ten consecutive runs, so the remaining
  cost is latency and the lookups are issued concurrently.
* Because the gate `if(cursor.rowcount >= 1)` was therefore always false,
  everything behind it never ran — including the four Config_Sources calls
  that produce ignition, mileage, fuel and driver ID. Those read
  dll_device_local_configs in Cassandra, which IS populated: all three sampled
  devices have exactly one row per parameter, and the ignition source 'in5'
  matches the event_uid on these fixes. So this restores real data.

Three bugs in the code the gate was hiding, all pre-existing
-----------------------------------------------------------
1. IO_ID_Found was assigned only for 'ruptela' and 'teltonika'. This unit is
   'xirgo_global' -> NameError on the first fix.
2. IO_NameValue_adapter[0] after cursor.fetchone(). dll_io_events_config holds
   ZERO rows, so every id misses and None[0] is a TypeError.
3. ORDER BY data_idx DESC is an integer sort in Postgres; data_idx is `text`
   in Cassandra and the table has no clustering column. Ordering now happens
   in io_events_store, numerically.

Why a line range instead of an exact string match
-------------------------------------------------
The block being replaced carries trailing whitespace on several lines.
Reproducing it by hand to match exactly is how a patch silently edits
nothing. This locates the block by its first and last statement, asserts six
markers are inside it, and refuses if anything is off.

    python scripts/patch_b5_io_events.py            # dry run
    python scripts/patch_b5_io_events.py --apply
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

IMPORT_ANCHOR = 'from . import location_store\n'
IMPORT_LINE = 'from . import io_events_store\n'

MUST_CONTAIN = ('dll_io_events_executed_logs', 'cursor.rowcount >= 1',
                "TheDeviceVendor == 'ruptela'", 'IO_NameValue_adapter[0]',
                'io_events_Found.append', 'io_events_dataAdapter')

PREFETCH = """
                                    # Every fix's IO events in one go. The old
                                    # per-fix Postgres lookup scanned 11 GB to
                                    # return nothing — that table holds none of
                                    # these uids — so the gate below was always
                                    # false and the Config_Sources calls after
                                    # it never ran.
                                    try:
                                        _io_by_uid = io_events_store.events_for(
                                            get_cassandra_session(),
                                            [_t[5] for _t in trips_data_adapter])
                                    except io_events_store.IoEventsUnavailable as _io_error:
                                        # "We could not look" must not render as
                                        # "this vehicle reported nothing".
                                        logging.warning(
                                            "trips_history: IO events unavailable "
                                            "for %s: %s", DeviceImei, _io_error)
                                        return reply('error', 503, 'Telemetry detail is temporarily unavailable, please retry', '')

                                    # One query for every distinct channel id,
                                    # not one per IO event. Returns {} when the
                                    # reference table is empty, which it is.
                                    _io_names = io_events_store.names_for(
                                        cursor, TableName, ValueColunmName,
                                        ConditionColunmName,
                                        [io_events_store.vendor_io_id(
                                            TheDeviceVendor, _event['event_uid'])
                                         for _list in _io_by_uid.values()
                                         for _event in _list])
"""

REPLACEMENT = """                                        _events = _io_by_uid.get(
                                            str(RecordIO_UID or '').strip(), [])

                                        if _events:

                                            io_events_Found = []
                                            enduser_data = []

                                            for io_event in _events:

                                                # Every vendor, not two of them.
                                                # This unit is xirgo_global, and
                                                # the old code assigned nothing
                                                # here -> NameError.
                                                IO_ID_Found = io_events_store.vendor_io_id(
                                                    TheDeviceVendor, io_event['event_uid'])

                                                # dll_io_events_config has no
                                                # rows, so this misses and the
                                                # raw channel id is the label.
                                                # The old code did fetchone()[0]
                                                # on None.
                                                IO_NameValue_Extracted = _io_names.get(
                                                    IO_ID_Found, IO_ID_Found)

                                                SingleIO_Event = {
                                                    IO_NameValue_Extracted: io_event['value']
                                                }

                                                io_events_Found.append(SingleIO_Event)
"""


def span(lines, name):
    start = next((i for i, l in enumerate(lines)
                  if re.match(rf'def {name}\(', l)), None)
    if start is None:
        return None, None
    end = next((j for j in range(start + 1, len(lines))
                if re.match(r'def \w+\(|@\w+\.route\(', lines[j])), len(lines))
    return start, end


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

    if 'io_events_store.events_for(' in src:
        print('Already patched. Nothing to do.')
        return 0

    lines = src.splitlines(keepends=True)
    lo, hi = span(lines, FUNC)
    if lo is None:
        print(f'!! def {FUNC}( not found')
        return 1

    first = next((i for i in range(lo, hi)
                  if 'dll_io_events_executed_logs' in lines[i]
                  and 'cursor.execute' in lines[i]), None)
    last = next((i for i in range(first or lo, hi)
                 if 'io_events_Found.append(SingleIO_Event)' in lines[i]), None)
    if first is None or last is None or last <= first:
        print('!! could not locate the block inside '
              f'{FUNC}() (first={first}, last={last})')
        return 1

    block = ''.join(lines[first:last + 1])
    missing = [m for m in MUST_CONTAIN if m not in block]
    if missing:
        print('!! the block is not what this patch was written against.')
        for m in missing:
            print(f'     missing marker: {m!r}')
        return 1
    if 'Config_Sources' in block:
        print('!! the block reaches past the IO loop into the '
              'Config_Sources calls; refusing.')
        return 1
    print(f'block located: lines {first + 1}-{last + 1} '
          f'({last - first + 1} lines), all {len(MUST_CONTAIN)} markers present')

    loop = next((i for i in range(lo, first)
                 if lines[i].strip() == 'for trip in trips_data_adapter:'), None)
    if loop is None:
        print('!! could not find "for trip in trips_data_adapter:" to insert '
              'the prefetch before')
        return 1
    print(f'prefetch goes in before line {loop + 1}')

    new_lines = (lines[:loop] + [PREFETCH.lstrip('\n'), '\n']
                 + lines[loop:first] + [REPLACEMENT] + lines[last + 1:])
    new = ''.join(new_lines)
    if IMPORT_LINE not in new:
        if IMPORT_ANCHOR not in new:
            print(f'!! import anchor missing: {IMPORT_ANCHOR.strip()}')
            return 1
        new = new.replace(IMPORT_ANCHOR, IMPORT_ANCHOR + IMPORT_LINE, 1)

    try:
        compile(new, TARGET, 'exec')
    except SyntaxError as error:
        print(f'!! the patched file does not compile: line {error.lineno}: '
              f'{error.msg}\n   Nothing written.')
        return 1
    print('the patched file compiles')

    for line in difflib.unified_diff(src.splitlines(), new.splitlines(),
                                     fromfile='data.py (now)',
                                     tofile='data.py (patched)',
                                     lineterm='', n=2):
        print(line)

    if not args.apply:
        print('\n--- DRY RUN. Nothing written. ---')
        print('    python scripts/patch_b5_io_events.py --apply')
        return 0

    backup = f'{TARGET}.bak.{time.strftime("%Y%m%d-%H%M%S")}'
    shutil.copy2(TARGET, backup)
    io.open(TARGET, 'w', encoding='utf-8', newline='').write(
        new.replace('\n', '\r\n') if crlf else new)
    print(f'\nwritten. backup at {backup}')
    print('\nThen:')
    print('  python scripts/b5_measure.py')
    print('\nExpect the response to CHANGE — ignition, mileage, fuel and')
    print('driver should appear where they were absent. That is the fix, not')
    print('a regression; b5_measure will flag it as a difference and print it.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
