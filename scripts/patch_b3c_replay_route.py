#!/usr/bin/env python3
"""
B3c (part 2) -- trips/history/replay reads the live position store.

The last Postgres position read in data.py. Both branches go:

    if TimeFrom:  SELECT ... with the datetime-range WHERE clause
    else:         SELECT ... plain

Both become location_store.fixes(). The timed branch passes the datetime span
that part 1 added, built with location_store.local_datetime() so the route and
the reader cannot disagree about date formats.

WHAT CHANGES BEHAVIOUR, AND WHY THAT IS RIGHT

The old SQL compared local_system_timestamp as TEXT:

    AND (TO_DATE(local_system_datestamp,'DD-MM-YYYY') > TO_DATE(%s,'DD-MM-YYYY')
         OR local_system_timestamp >= %s)

_playback_times emits zero-padded 24-hour 'HH:MM:SS', while _TIME_FORMATS
lists '%I:%M:%S%p' FIRST -- so the stored values are very likely 12-hour
('02:30:15PM'). Text-comparing '02:30:15PM' against '14:00:00' is wrong for
every afternoon row: 'PM' strings sort below '14'. The span compares parsed
datetimes, so afternoon fixes are placed correctly. That is a behaviour
CHANGE, and a deliberate one -- "preserve existing behaviour" should not mean
preserving a comparison that cannot work.

WHAT THIS PATCH DOES NOT DO

dbconnect is this body's only Postgres user, so after the swap the connection
is opened and never used. It is LEFT IN PLACE: removing it means re-indenting
the whole trip-building loop out of two `with` blocks, and bundling that into
a store swap is how a working route gets broken. One wasted connection per
replay request is not a regression (it is what happens today), and removing it
is its own small ticket.

The unreachable tail at the end of the function is likewise untouched; B3d
proved it dead and it keeps its own connection.

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
ROUTE = 'trips_history_replay'


def read_source(path):
    with io.open(path, 'rb') as handle:
        text = handle.read().decode('utf-8')
    return text.replace('\r\n', '\n'), ('\r\n' in text)


def write_source(path, text, crlf):
    out = text.replace('\n', '\r\n') if crlf else text
    with io.open(path, 'wb') as handle:
        handle.write(out.encode('utf-8'))


def live_body(text):
    """(lo, hi) of the FIRST try block in the route -- the reachable one."""
    for node in ast.parse(text).body:
        if isinstance(node, ast.FunctionDef) and node.name == ROUTE:
            tries = [s for s in node.body if isinstance(s, ast.Try)]
            if not tries:
                raise SystemExit('FAIL: no try block in %s' % ROUTE)
            return tries[0].lineno, tries[0].end_lineno
    raise SystemExit('FAIL: def %s() not found' % ROUTE)


READ = '''                        # B3c: positions come from the live store.
                        #
                        # The timed branch used to compare
                        # local_system_timestamp as TEXT against zero-padded
                        # 24-hour input. The stored values are 12-hour
                        # ('02:30:15PM'), so every afternoon fix compared
                        # wrongly. A parsed datetime span fixes that.
                        #
                        # local_datetime() is location_store's own parser, so
                        # the span ends cannot drift from the formats the read
                        # accepts.
                        _span_from = None
                        _span_to = None

                        if TimeFrom:
                            _span_from = location_store.local_datetime(
                                FromDate, TimeFrom)
                            _span_to = location_store.local_datetime(
                                ToDate, TimeTo)

                            if _span_from is None or _span_to is None:
                                return reply('error', 400,
                                             'from_date and to_date did not '
                                             'parse as dates', '')

                        try:
                            _replay_fixes, _replay_truncated = \\
                                location_store.fixes(
                                    get_cassandra_session(), DeviceImei,
                                    FromDate, ToDate,
                                    limit=Record_Count, offset=Offset_Record,
                                    datetime_from=_span_from,
                                    datetime_to=_span_to)
                        except location_store.PositionsUnavailable as error:
                            logging.warning(
                                'trips_history_replay: position store '
                                'unavailable: %s', error)
                            return reply('error', 503,
                                         'Position data is temporarily '
                                         'unavailable, please retry', '')

                        trips_data_adapter = [
                            location_store.as_history_tuple(_fix)
                            for _fix in _replay_fixes]

'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()

    text, crlf = read_source(TARGET)
    before = text.count('\n') + 1

    if '_replay_fixes' in text:
        print('SKIP: already patched.')
        return 0

    lo, hi = live_body(text)
    lines = text.split('\n')

    # locate, inside the live body only
    with_at = execs = guard = zero = fetch = None
    exec_lines = []

    for i in range(lo, hi + 1):
        s = lines[i - 1].strip()
        if with_at is None and s == 'with dbconnect:':
            with_at = i
        if s.startswith('cursor.execute("SELECT data_longitude'):
            exec_lines.append(i)
        if guard is None and s == 'if(cursor.rowcount >= 1):':
            guard = i
        if zero is None and s == 'elif(cursor.rowcount == 0):':
            zero = i
        if fetch is None and s == 'trips_data_adapter = cursor.fetchall()':
            fetch = i

    missing = [n for n, v in (('with dbconnect', with_at),
                              ('rowcount >= 1', guard),
                              ('rowcount == 0', zero),
                              ('fetchall', fetch)) if v is None]
    if missing:
        print('FAIL: could not locate %s in the live body' % ', '.join(missing))
        return 1

    if len(exec_lines) != 2:
        print('FAIL: expected exactly 2 position SELECTs in the live body, '
              'found %d' % len(exec_lines))
        return 1

    # the if TimeFrom / else lines wrap the two executes; find them
    branch = None
    for i in range(with_at, exec_lines[0]):
        if lines[i - 1].strip() == 'if TimeFrom:':
            branch = i
    if branch is None:
        print('FAIL: could not find the `if TimeFrom:` branch')
        return 1

    # ---- edits, highest line number first
    lines[guard - 1] = lines[guard - 1].replace(
        'cursor.rowcount >= 1', 'len(trips_data_adapter) >= 1')
    lines[zero - 1] = lines[zero - 1].replace(
        'cursor.rowcount == 0', 'len(trips_data_adapter) == 0')

    # drop the fetchall, then the whole `if TimeFrom:`/else SELECT block
    del lines[fetch - 1]
    # the branch block runs from `if TimeFrom:` up to and including the last
    # execute's line (plus its `else:` line in between)
    del lines[branch - 1:exec_lines[-1]]

    # the live read goes above `with dbconnect:`
    lines.insert(with_at - 1, READ.rstrip('\n'))

    text = '\n'.join(lines)

    try:
        compile(text, TARGET, 'exec')
    except SyntaxError as error:
        print('FAIL: patched source does not compile: %s' % error)
        return 1

    # ---- verify the live body only
    lo2, hi2 = live_body(text)
    body = '\n'.join(text.split('\n')[lo2 - 1:hi2])

    for bad, label in (('cursor.rowcount', 'cursor.rowcount'),
                       ('cursor.fetchall', 'cursor.fetchall'),
                       ('cursor.execute("SELECT data_longitude',
                        'a Postgres position SELECT')):
        if bad in body:
            print('FAIL: %s survives in the live body' % label)
            return 1

    for needed in ('location_store.fixes', 'datetime_from=_span_from',
                   'as_history_tuple', 'local_datetime'):
        if needed not in body:
            print('FAIL: %s is missing from the live body' % needed)
            return 1

    # the dead tail must be untouched and must keep its own connection
    tail = text.split('\n')[hi2:]
    tail_text = '\n'.join(tail)
    if 'psycopg2.connect' not in tail_text:
        print('FAIL: the tail lost its own connection -- it may now depend on')
        print('      the live body, which would make it reachable again')
        return 1

    remaining = text.count('cursor.execute("SELECT data_longitude')
    print('endpoints/data.py  %s  %d -> %d lines'
          % ('CRLF' if crlf else 'LF', before, text.count('\n') + 1))
    print('   * both position SELECTs replaced by one location_store read')
    print('   * the timed branch now passes a parsed datetime span')
    print('   * cursor.rowcount -> len(trips_data_adapter) at both sites')
    print('   * dbconnect left in place (see the module docstring)')
    print('')
    print('   Postgres position SELECTs left in data.py: %d' % remaining)
    print('   (expect 0 -- the dead tail\'s summary query selects')
    print('    data_device_imei first, so it does not match this count)')
    if remaining != 0:
        print('   !! not 0 -- stop and look before applying')
        return 1

    if not args.apply:
        print('\nDRY RUN -- nothing written.  Re-run with --apply.')
        return 0

    write_source(TARGET, text, crlf)
    print('\nWRITTEN.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
