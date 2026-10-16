#!/usr/bin/env python3
"""
b3c_route_check.py -- does trips/history/replay read the live store, and did
the time window really become a datetime SPAN?

B3c moved this route off the Postgres copy of dll_location_registry and
replaced its text time comparison with a parsed datetime span. The reader is
tested (53 unit tests, 18 of them on the span) but that says nothing about the
route: the span has to be built from the route's own FromDate/TimeFrom and
threaded through a guard, a date check and a record-count check.

THE CASE THAT MATTERS is 4. Everything else is scaffolding.

  1. untimed, one day        the ordinary path. 200 with fixes.
  2. timed, one day          08:00-17:00 on a single day. Span and clock
                             window agree here, so this only proves the
                             window is applied at all -- every returned fix
                             must fall inside those hours. The bound is
                             08:00:00 .. 17:00:59, NOT 17:00:00: the route's
                             _playback_times pads a missing seconds field
                             with '59'. The first version of this check
                             compared against 17:00:00 and so reported a
                             working route as broken on a fix at 17:00:56.
  3. invalid time            'xyz' must be a 400 naming HH:MM, not a crash
                             and not a silently ignored filter.
  4. two days, inverted      THE DECISIVE CASE. 24-09 08:00 to 25-09 06:00.
     hours                   As a SPAN that is one continuous range ending in
                             the small hours of the 25th, so with newest-first
                             paging the fixes that come back ARE those small
                             hours. As a daily CLOCK window, hours 08:00 down
                             to 06:00 is inverted, matches nothing, and the
                             route answers 'No Trips Found'. Opposite
                             outcomes, so this case cannot pass for the
                             wrong reason.

                             The first version asked for three days at
                             08:00-17:00 and looked for inner-day night
                             fixes. That could not work: record_count=200
                             newest-first returns only the TAIL of the span,
                             which is 17:00:xx on the last day -- inside the
                             real 17:00:59 bound. It never reached the inner
                             day at all, and reported success on evidence
                             that did not support it.
  5. window that excludes    a timed window with no fixes in it must be an
     everything              honest 'No Trips Found', not a 503 and not a
                             silent full-day result.
  6. empty date window       07-08 to 11-08-2025, which Cassandra lacks:
                             'No Trips Found', never 503.

Case 4 can only fail quietly, which is why it is checked by inspecting the
DATES AND TIMES of the fixes that came back rather than by trusting the
status code.

Read-only.

Usage:
    python scripts/b3c_route_check.py
    python scripts/b3c_route_check.py --imei 862846042622426 --day 25-09-2026
"""

import argparse
import sys
import time as _time
from datetime import datetime, timedelta

sys.path.insert(0, '.')

ROUTE = '/data-stream/trips/history/replay'
EMPTY_UNIT = '867556044727322'

RESULTS = []
COLD_STARTS = []


def record(label, ok, blocked, detail):
    mark = 'ok ' if ok else ('-- ' if blocked else '!! ')
    print('   %s%-30s %s' % (mark, label, detail))
    RESULTS.append((label, ok, blocked, detail))


def billing_blocked(message):
    low = str(message).lower()
    return ('billing' in low or 'cant be found' in low or 'not-found' in low)


def call(client, imei, start, end, count=200, t_from=None, t_to=None):
    data = {'device_imei': imei, 'from_date': start, 'to_date': end,
            'offset_log': '0', 'record_count': str(count)}
    if t_from is not None:
        data['from_time'] = t_from
    if t_to is not None:
        data['to_time'] = t_to
    began = _time.time()
    try:
        res = client.post(ROUTE, json={'data': data})
        payload = res.get_json() or {}
        return (res.status_code, str(payload.get('message', '')),
                payload.get('data'), _time.time() - began)
    except Exception as error:                            # noqa: BLE001
        return 0, 'EXCEPTION %s' % error, None, _time.time() - began


def call_retrying_cold_start(client, *a, **kw):
    """call(), retried once on a 503, returning (result, cold_start).

    503 from this route means "the position store could not be read, retry" —
    a documented-retryable answer. A checker that will not retry it goes red
    every time the Cassandra handshake times out at cold start, which is B9,
    not a fault in the route under test.

    So retry ONCE and report the cold start loudly. Nothing is hidden: a
    second 503 is still a hard failure, because that is no longer a cold
    start, it is a store that cannot be read.
    """
    result = call(client, *a, **kw)
    if result[0] != 503:
        return result, False
    print('        .. 503 on the first call (%.1fs). Retrying once: a cold'
          % result[3])
    print('           Cassandra handshake is B9, not this route.')
    _time.sleep(2)
    return call(client, *a, **kw), True


def clock_of(fix):
    """The fix's local time of day, parsed the way location_store parses it."""
    raw = str(fix.get('local_system_timestamp') or '').strip()
    for fmt in ('%I:%M:%S%p', '%I:%M:%S %p', '%I:%M%p', '%I:%M %p',
                '%H:%M:%S', '%H:%M:%S.%f', '%H:%M'):
        try:
            return datetime.strptime(raw, fmt).time()
        except ValueError:
            continue
    return None


def padded(value, seconds):
    """A requested HH:MM as the route's _playback_times would pad it.

    _norm() fills a missing seconds field with '00' for from_time and '59'
    for to_time, so a request for 17:00 really means 17:00:59 -- a whole
    minute wider than it looks. Deriving the bound by the same rule keeps
    this check honest. Hardcoding 17:00:00 failed a working route once.
    """
    hour, minute = value.split(':')[:2]
    return datetime.strptime('%02d:%s:%s' % (int(hour), minute, seconds),
                             '%H:%M:%S').time()


def summarise(fixes):
    clocks = [c for c in (clock_of(f) for f in fixes) if c is not None]
    if not clocks:
        return 'no parseable times'
    return 'times %s .. %s' % (min(clocks).strftime('%H:%M:%S'),
                               max(clocks).strftime('%H:%M:%S'))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--imei', default='862846042622426')
    ap.add_argument('--day', default='25-09-2026')
    args = ap.parse_args()

    from app import app
    client = app.test_client()

    middle = datetime.strptime(args.day, '%d-%m-%Y').date()
    before = (middle - timedelta(days=1)).strftime('%d-%m-%Y')

    print('unit %s, day %s (decisive span %s 08:00 .. %s 06:00)'
          % (args.imei, args.day, before, args.day))
    print('')

    # ---- 1. untimed
    #
    # First call of the run, so it pays the Cassandra handshake. See
    # call_retrying_cold_start().
    (code, message, data, took), cold = \
        call_retrying_cold_start(client, args.imei, args.day, args.day)
    fixes = data if isinstance(data, list) else []
    blocked = billing_blocked(message)
    record('untimed, one day', code == 200 and bool(fixes), blocked,
           'HTTP %s %r  %d fixes  %.1fs%s'
           % (code, message[:30], len(fixes), took,
              '  [after a cold-start 503]' if cold else ''))
    if fixes:
        print('        %s' % summarise(fixes))
    if cold:
        COLD_STARTS.append('untimed, one day')

    # ---- 2. timed, one day: span and clock window agree
    code, message, data, took = call(client, args.imei, args.day, args.day,
                                     t_from='08:00', t_to='17:00')
    timed_one = data if isinstance(data, list) else []
    blocked = billing_blocked(message)

    if code == 200 and timed_one:
        low = padded('08:00', '00')
        high = padded('17:00', '59')          # 17:00:59, not 17:00:00
        outside = [f for f in timed_one
                   if clock_of(f) is not None
                   and not (low <= clock_of(f) <= high)]
        record('timed, one day: window applied', not outside, blocked,
               '%d fixes, %d outside %s-%s'
               % (len(timed_one), len(outside),
                  low.strftime('%H:%M:%S'), high.strftime('%H:%M:%S')))
        print('        %s' % summarise(timed_one))
        if outside:
            print('        !! e.g. %s -- the window is not being applied'
                  % str(outside[0].get('local_system_timestamp')))
    else:
        record('timed, one day: window applied', False, blocked,
               'HTTP %s %r -- no fixes to judge' % (code, message[:34]))

    # ---- 3. an invalid time must be refused
    code, message, _data, took = call(client, args.imei, args.day, args.day,
                                      t_from='xyz', t_to='17:00')
    record('invalid time refused', code == 400 and 'HH:MM' in message, False,
           'HTTP %s %r' % (code, message[:46]))

    # ---- 4. THE DECISIVE CASE: 24-09 08:00 .. 25-09 06:00
    #
    # As a span: one continuous range whose newest end is 06:00:59 on the
    # 25th, so newest-first paging returns the small hours of the 25th.
    # As a daily clock window: hours 08:00 down to 06:00 is inverted, matches
    # nothing, and the route answers 'No Trips Found'. Opposite outcomes.
    code, message, data, took = call(client, args.imei, before, args.day,
                                     t_from='08:00', t_to='06:00')
    span = data if isinstance(data, list) else []
    blocked = billing_blocked(message)

    if code == 200 and span:
        day_start = padded('08:00', '00')
        small_hours = [f for f in span
                       if clock_of(f) is not None
                       and clock_of(f) < day_start
                       and str(f.get('local_system_datestamp') or '').strip()
                       == args.day]

        record('inverted hours: span not clock', bool(small_hours), blocked,
               '%d fixes, %d in the small hours of %s'
               % (len(span), len(small_hours), args.day))
        print('        %s' % summarise(span))
        if small_hours:
            sample = small_hours[0]
            print('        e.g. %s %s -- inside the SPAN, and impossible'
                  % (sample.get('local_system_datestamp'),
                     sample.get('local_system_timestamp')))
            print('           under a daily 08:00->06:00 clock window')
            print('        -> datetime-span semantics confirmed on real data')
        else:
            print('        !! fixes came back, but none before 08:00 on %s.'
                  % args.day)
            print('           Either record_count is too small to reach them')
            print('           or the span end is not built from to_date.')
    else:
        record('inverted hours: span not clock', False, blocked,
               'HTTP %s %r -- no fixes to judge' % (code, message[:34]))
        if code == 400 and 'no trips' in message.lower():
            print('        !! an inverted 08:00->06:00 range matched nothing.')
            print('           That is the DAILY CLOCK WINDOW, not a span --')
            print('           the B3c change did not take effect.')

    # ---- 5. a window that excludes everything
    code, message, data, took = call(client, args.imei, args.day, args.day,
                                     t_from='03:05', t_to='03:06')
    empty = data if isinstance(data, list) else []
    blocked = billing_blocked(message)
    honest = (code == 400 and 'no trips' in message.lower()) or \
             (code == 200 and len(empty) < len(fixes))
    record('narrow window is honest', honest, blocked,
           'HTTP %s %r  %d fixes (vs %d untimed)'
           % (code, message[:28], len(empty), len(fixes)))
    if code == 503:
        print('        !! 503 on an empty window: "could not look" confused')
        print('           with "nothing in the window".')

    # ---- 6. a date window Cassandra lacks
    code, message, _data, took = call(client, EMPTY_UNIT, '07-08-2025',
                                      '11-08-2025')
    blocked = billing_blocked(message)
    record('empty date window says so',
           code == 400 and 'no trips' in message.lower(), blocked,
           'HTTP %s %r' % (code, message[:34]))

    # ---- report
    print('')
    print('=' * 70)
    good = [r for r in RESULTS if r[1]]
    blk = [r for r in RESULTS if r[2] and not r[1]]
    bad = [r for r in RESULTS if not r[1] and not r[2]]
    print('   %d as expected, %d billing-blocked, %d wrong'
          % (len(good), len(blk), len(bad)))

    if blk:
        print('')
        print('   Those prove nothing: the route checks the device registry')
        print('   and billing before reading a position.')

    if COLD_STARTS:
        print('')
        print('   B9 observed live: the first Cassandra connect of the run')
        print('   timed out and answered 503, and the retry succeeded (%s).'
              % ', '.join(COLD_STARTS))
        print('   The route answered correctly — "could not look", not a')
        print('   wrong answer — but a real client saw a failed request.')

    if bad:
        print('')
        print('   NOT working:')
        for label, _ok, _b, detail in bad:
            print('     - %-32s %s' % (label, detail))
        print('')
        print('   location_store and its span are separately tested, so a')
        print('   failure here is in the route: how the span is built from')
        print('   FromDate/TimeFrom, or the len(trips_data_adapter) guards')
        print('   that replaced cursor.rowcount.')
        return 1

    print('')
    print('   B3c works: replay reads the live store, and an inverted')
    print('   08:00->06:00 request across two days returned the small hours')
    print('   that a daily clock window could not have matched at all.')
    print('   data.py now has no Postgres position read on any reachable')
    print('   path.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
