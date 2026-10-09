#!/usr/bin/env python3
"""
B3 (part 1) -- trips/excel and trips/pdf read the live position store.

Both routes query the Postgres copy of dll_location_registry, which ends
01-08-2025 while the Cassandra store begins 05-08-2025. The two share no day
(established in B1), so for any recent date these exports return NOTHING --
the same failure B2 fixed for trips/history. The web view now works and the
exports do not, which reads to a customer as a broken export rather than a
dead data source.

Their main queries are BYTE-IDENTICAL to each other and to the one B2 already
replaced:

    PARTITION BY data_longitude, data_latitude ORDER BY data_idx DESC
      ... row_num = 1 ... ORDER BY data_idx DESC LIMIT %s OFFSET %s

which is exactly fixes(dedupe_coordinates=True, limit, offset,
newest_first=True) followed by as_history_tuple. So this is a substitution,
not a reimplementation.

THREE THINGS THIS PATCH IS CAREFUL ABOUT

1. The position read moves ABOVE `with dbconnect:`. ComputeTrips_EXCELL
   INSERTs a row into dll_reports_downloadable_files before reading, and
   `with dbconnect:` commits on exit -- including on a `return`. Returning 503
   from inside it would leave an orphan report row stuck in its initial state.
   Reading first means a 503 happens before any bookkeeping exists.

2. The Postgres connection STAYS. Both routes write the report-file
   bookkeeping (INSERT, then UPDATE to completed / no-data / failed). Only the
   position read moves. And it stays their OWN connection: B7's shared
   read-only connection commits when its `with` block exits, so it must never
   be handed to a writer.

3. `cursor.rowcount` becomes `len(raw_data_adapter)` at BOTH sites in each
   route -- the `>= 1` guard and the `== 0` no-data branch. Missing the second
   would leave a route that can never report "no data".

Not touched: Trip[-1] is read as the row number at four call sites, and
as_history_tuple keeps row_index last, so those keep working. (This is also
why B4's stop fields went to a separate route rather than being appended to
this tuple -- appending would have made Trip[-1] return drift_m and silently
corrupted every export's row numbers.)

Dry run by default. Pass --apply to write.
"""

import argparse
import ast
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TARGET = os.path.join(ROOT, 'endpoints', 'data.py')

ROUTES = ('ComputeTrips_EXCELL', 'ComputeTrips_PDF')


def read_source(path):
    with io.open(path, 'rb') as handle:
        text = handle.read().decode('utf-8')
    return text.replace('\r\n', '\n'), ('\r\n' in text)


def write_source(path, text, crlf):
    out = text.replace('\n', '\r\n') if crlf else text
    with io.open(path, 'wb') as handle:
        handle.write(out.encode('utf-8'))


def function_range(text, name):
    for node in ast.parse(text).body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node.lineno, node.end_lineno
    raise SystemExit('FAIL: def %s() not found' % name)


READ_BLOCK = '''            # B3: positions come from the live store.
            #
            # The Postgres copy of dll_location_registry ends 01-08-2025 and
            # the Cassandra store begins 05-08-2025 -- no shared day -- so this
            # export returned nothing for every recent date.
            #
            # Read BEFORE `with dbconnect:` on purpose: that block commits when
            # it exits, a `return` included, so a 503 raised inside it would
            # leave an orphan row in dll_reports_downloadable_files.
            try:
                _position_fixes, _positions_truncated = location_store.fixes(
                    get_cassandra_session(), DeviceImei, FromDate, ToDate,
                    limit=Record_Count, offset=Offset_Record)
            except location_store.PositionsUnavailable as error:
                logging.warning('__ROUTE__: position store unavailable: %s',
                                error)
                return reply('error', 503,
                             'Position data is temporarily unavailable, '
                             'please retry', '')

            raw_data_adapter = [location_store.as_history_tuple(_fix)
                                for _fix in _position_fixes]

'''


def patch_route(text, name):
    lo, hi = function_range(text, name)
    lines = text.split('\n')
    body = lines[lo - 1:hi]

    # locate, within this function only
    select_at = None
    with_at = None
    fetch_at = None
    guard_at = None
    nodata_at = None

    for offset, line in enumerate(body):
        stripped = line.strip()
        if select_at is None and stripped.startswith(
                'cursor.execute("SELECT data_longitude'):
            select_at = offset
        if with_at is None and stripped == 'with dbconnect:':
            with_at = offset
        if fetch_at is None and stripped == 'raw_data_adapter = cursor.fetchall()':
            fetch_at = offset
        if guard_at is None and stripped == 'if(cursor.rowcount >= 1):':
            guard_at = offset
        if nodata_at is None and stripped == 'elif(cursor.rowcount == 0):':
            nodata_at = offset

    missing = [n for n, v in (('SELECT', select_at), ('with dbconnect', with_at),
                              ('fetchall', fetch_at), ('rowcount >= 1', guard_at),
                              ('rowcount == 0', nodata_at)) if v is None]
    if missing:
        print('FAIL [%s]: could not locate %s' % (name, ', '.join(missing)))
        return None, []

    if not (with_at < select_at < guard_at < fetch_at < nodata_at):
        print('FAIL [%s]: sites are not in the expected order' % name)
        return None, []

    steps = []

    # 1. rowcount -> len(raw_data_adapter), both sites
    body[guard_at] = body[guard_at].replace('cursor.rowcount >= 1',
                                            'len(raw_data_adapter) >= 1')
    body[nodata_at] = body[nodata_at].replace('cursor.rowcount == 0',
                                              'len(raw_data_adapter) == 0')
    steps.append('rowcount -> len(raw_data_adapter) at both sites')

    # 2. drop the SELECT and the fetchall (highest index first)
    for offset in sorted((select_at, fetch_at), reverse=True):
        del body[offset]
    steps.append('removed the Postgres SELECT and the fetchall')

    # 3. the live read, above `with dbconnect:`
    body.insert(with_at, READ_BLOCK.rstrip('\n').replace('__ROUTE__', name))
    steps.append('inserted the location_store read above `with dbconnect:`')

    return lines[:lo - 1] + body + lines[hi:], steps


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()

    text, crlf = read_source(TARGET)
    before = text.count('\n') + 1

    if '_position_fixes' in text:
        print('SKIP: already patched.')
        return 0

    for name in ROUTES:
        new_lines, steps = patch_route(text, name)
        if new_lines is None:
            return 1
        text = '\n'.join(new_lines)
        print('%s' % name)
        for step in steps:
            print('   * %s' % step)

    try:
        compile(text, TARGET, 'exec')
    except SyntaxError as error:
        print('FAIL: patched source does not compile: %s' % error)
        return 1

    # nothing outside the two routes may have changed
    for name in ROUTES:
        lo, hi = function_range(text, name)
        chunk = '\n'.join(text.split('\n')[lo - 1:hi])
        if 'cursor.rowcount' in chunk:
            print('FAIL: %s still references cursor.rowcount' % name)
            return 1
        if 'location_store.fixes' not in chunk:
            print('FAIL: %s does not read location_store' % name)
            return 1

    remaining = text.count('cursor.execute("SELECT data_longitude')
    summary = text.count('cursor.execute("SELECT data_device_imei')
    print('')
    print('endpoints/data.py  %s  %d -> %d lines'
          % ('CRLF' if crlf else 'LF', before, text.count('\n') + 1))
    print('   Postgres position reads left, by column order:')
    print('     SELECT data_longitude ...   %d  (expect 2: the two replay'
          % remaining)
    print('                                     branches, out of scope here)')
    print('     SELECT data_device_imei ... %d  (expect 1: the summary query in'
          % summary)
    print("                                     replay's unreachable tail)")
    if remaining != 2 or summary != 1:
        print('   !! not the expected 2 and 1 -- stop and look before applying')
        return 1

    if not args.apply:
        print('\nDRY RUN -- nothing written.  Re-run with --apply.')
        return 0

    write_source(TARGET, text, crlf)
    print('\nWRITTEN.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
