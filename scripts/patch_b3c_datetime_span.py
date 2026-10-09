#!/usr/bin/env python3
"""
B3c (part 1) -- location_store gains a DATETIME SPAN filter.

The replay route's time window is a datetime range, not a daily clock window.
Its own comment says so:

    points on the first day from TimeFrom, on the last day up to TimeTo,
    everything on the days between

location_store already has time_from/time_to, and its docstring claims they
exist "as the replay route passes" -- but they filter at.time() on EVERY day,
which is a different thing. For 01-05 Oct 08:00-17:00 the SQL returns the night
hours on the 2nd to 4th and the clock window excludes them. They agree only
when from_date == to_date, and nothing forces that.

So this adds datetime_from / datetime_to alongside the existing pair rather
than redefining it: any caller using the clock window keeps it.

TWO DELIBERATE DIFFERENCES FROM THE SQL IT REPLACES

1. It compares PARSED DATETIMES, not text. The SQL does
       local_system_timestamp >= '14:00:00'
   as a string comparison, and _TIME_FORMATS lists '%I:%M:%S%p' FIRST, so the
   stored values are very likely 12-hour ('02:30:15PM'). Text-comparing those
   against zero-padded 24-hour input is wrong for every afternoon row. The
   span filter uses _stamp()'s parsed value, which handles both formats, so
   this removes that bug instead of porting it.

2. A fix that cannot be placed in time is EXCLUDED from a span, where the
   clock window lets it through. `if (low or high) and at is not None` means a
   row with an unparseable local timestamp currently passes the clock filter.
   That is defensible for "only these hours" but not for "between these two
   moments": a point that cannot be shown to be inside the span must not be
   drawn on a replay line. The asymmetry is intentional and commented.

Dry run by default. Pass --apply to write.
"""

import argparse
import ast
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TARGET = os.path.join(ROOT, 'endpoints', 'location_store.py')


def read_source(path):
    with io.open(path, 'rb') as handle:
        text = handle.read().decode('utf-8')
    return text.replace('\r\n', '\n'), ('\r\n' in text)


def write_source(path, text, crlf):
    out = text.replace('\n', '\r\n') if crlf else text
    with io.open(path, 'wb') as handle:
        handle.write(out.encode('utf-8'))


# ---- 1. a public parser, so the route does not reach for _as_date/_as_time
HELPER = '''
def local_datetime(datestamp, timestamp=None, end_of_day=False):
    """A naive LOCAL datetime from a date and an optional time, or None.

    Public because the replay route needs to build the ends of a span from the
    same strings fixes() accepts, and must not reach into _as_date/_as_time to
    do it. Accepts every format _DATE_FORMATS and _TIME_FORMATS allow, so a
    caller cannot drift from what the reader understands.

    end_of_day fills a missing time with 23:59:59.999999 rather than midnight,
    so local_datetime(to_date, None, end_of_day=True) is the inclusive end of
    that day instead of its first instant.
    """
    day = _as_date(datestamp)
    if day is None:
        return None
    clock = _as_time(timestamp)
    if clock is None:
        clock = (datetime.max.time() if end_of_day else datetime.min.time())
    return datetime.combine(day, clock)

'''

# ---- 2. _row gains the span
OLD_ROW_DEF = '''def _row(r, low, high):
    """One Cassandra row as a fix, or None when it is unusable or falls outside
    the clock window."""'''
NEW_ROW_DEF = '''def _row(r, low, high, span_from=None, span_to=None):
    """One Cassandra row as a fix, or None when it is unusable or falls outside
    the clock window or the datetime span."""'''

OLD_CLOCK = '''    if (low or high) and at is not None:
        clock = at.time()
        if low and clock < low:
            return None
        if high and clock > high:
            return None
'''
NEW_CLOCK = '''    if (low or high) and at is not None:
        clock = at.time()
        if low and clock < low:
            return None
        if high and clock > high:
            return None

    # The datetime SPAN, which is not the clock window above.
    #
    # Note the asymmetry on `at is None`: the clock window lets an unplaceable
    # row through, this does not. "Only these hours" can reasonably keep a row
    # whose time is unreadable; "between these two moments" cannot, because a
    # point that cannot be shown to fall inside the span must not be drawn on
    # a replay line.
    if span_from is not None or span_to is not None:
        if at is None:
            return None
        if span_from is not None and at < span_from:
            return None
        if span_to is not None and at > span_to:
            return None
'''

# ---- 3. fixes() signature, docstring and the call through to _row
OLD_SIG = '''def fixes(session, imei, from_date, to_date,
          limit=None, offset=0, time_from=None, time_to=None,
          dedupe_coordinates=True, newest_first=True):'''
NEW_SIG = '''def fixes(session, imei, from_date, to_date,
          limit=None, offset=0, time_from=None, time_to=None,
          datetime_from=None, datetime_to=None,
          dedupe_coordinates=True, newest_first=True):'''

OLD_DOC = '''    time_from / time_to   optional clock window, as the replay route passes'''
NEW_DOC = '''    time_from / time_to   optional clock window: these hours on EVERY day in
                          the range. NOT what the replay route wants --
                          see datetime_from below.
    datetime_from /       optional continuous span: one range from an instant
    datetime_to           to an instant, which is what a replay is. Naive
                          local datetimes; build them with local_datetime().
                          A fix whose local timestamp will not parse is
                          excluded from a span (but not from a clock window)'''

OLD_CALL = '''        day_rows = [row for row in (_row(r, low, high) for r in found)
                    if row is not None]'''
NEW_CALL = '''        day_rows = [row for row in (_row(r, low, high, datetime_from,
                                          datetime_to) for r in found)
                    if row is not None]'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()

    text, crlf = read_source(TARGET)
    before = text.count('\n') + 1

    if 'def local_datetime(' in text:
        print('SKIP: already patched.')
        return 0

    steps = []

    for label, old, new in (
            ('_row() takes span_from / span_to', OLD_ROW_DEF, NEW_ROW_DEF),
            ('the span filter inside _row()', OLD_CLOCK, NEW_CLOCK),
            ('fixes() takes datetime_from / datetime_to', OLD_SIG, NEW_SIG),
            ('the docstring distinguishes the two', OLD_DOC, NEW_DOC),
            ('fixes() passes the span to _row()', OLD_CALL, NEW_CALL)):
        if text.count(old) != 1:
            print('FAIL: %s -- anchor found %d times, expected 1'
                  % (label, text.count(old)))
            return 1
        text = text.replace(old, new, 1)
        steps.append(label)

    # the helper goes immediately above _row
    anchor = 'def _row(r, low, high, span_from=None, span_to=None):'
    text = text.replace(anchor, HELPER.lstrip('\n') + '\n' + anchor, 1)
    steps.append('added the public local_datetime() helper')

    try:
        compile(text, TARGET, 'exec')
    except SyntaxError as error:
        print('FAIL: patched source does not compile: %s' % error)
        return 1

    # ---- verify
    tree = ast.parse(text)
    names = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
    if 'local_datetime' not in names:
        print('FAIL: local_datetime is not module level')
        return 1

    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == 'fixes':
            params = [a.arg for a in node.args.args]
            for needed in ('datetime_from', 'datetime_to', 'time_from',
                           'time_to', 'dedupe_coordinates', 'newest_first'):
                if needed not in params:
                    print('FAIL: fixes() lost parameter %s' % needed)
                    return 1
            # the old positional contract must be intact for existing callers
            if params[:6] != ['session', 'imei', 'from_date', 'to_date',
                              'limit', 'offset']:
                print('FAIL: the first six parameters of fixes() moved: %s'
                      % params[:6])
                return 1

    # Count the CALL and the DEF separately. '_row(r, low, high' is a prefix
    # of both the new def and the new call, so a single substring count
    # returns 2 on a correct edit -- the same containment mistake the B10
    # patch's own verification made.
    calls = text.count('_row(r, low, high, datetime_from')
    defs = text.count('def _row(r, low, high, span_from=None, span_to=None):')
    if calls != 1 or defs != 1:
        print('FAIL: expected 1 call and 1 def, found %d call(s) and %d def(s)'
              % (calls, defs))
        return 1

    print('endpoints/location_store.py  %s  %d -> %d lines'
          % ('CRLF' if crlf else 'LF', before, text.count('\n') + 1))
    for step in steps:
        print('   * %s' % step)
    print('')
    print('   existing callers unaffected: the first six positional')
    print('   parameters of fixes() are unchanged and the new ones are')
    print('   keyword-only in practice (they follow time_to).')

    if not args.apply:
        print('\nDRY RUN -- nothing written.  Re-run with --apply.')
        return 0

    write_source(TARGET, text, crlf)
    print('\nWRITTEN.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
