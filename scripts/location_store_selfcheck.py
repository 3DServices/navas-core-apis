#!/usr/bin/env python3
"""
location_store_selfcheck.py — prove the reader against the store it reads.

Why this exists
---------------
B1 was going to prove location_store by comparing it to the legacy Postgres
query. That is impossible: the window probe showed the two stores are disjoint
in time — Postgres stops on 06-08-2025 and Cassandra's rows for this unit start
after it. There is no shared data to compare.

So the question has to change. Not "does the new reader agree with the old
query" (unanswerable), but "does the new reader tell the truth about the rows
Cassandra actually holds" — which is what parity was really for.

How this avoids proving nothing
-------------------------------
The obvious approach is to re-implement dedupe and ordering here and check the
two agree. That proves only that I wrote the same thing twice. I made exactly
that mistake earlier in this work: I validated the old _points against data.py,
called it consistent, and called consistent correct — when both were reading a
dead table.

So this checks PROPERTIES derived from the raw rows instead, each one
independently computable and each one a thing that would be false if the reader
were wrong:

  1. No invention   every returned fix exists among the raw rows
  2. No loss        every distinct valid coordinate in raw is returned
  3. Dedupe exact   one returned row per distinct coordinate, no more
  4. Latest wins    each kept row is the newest for its coordinate, by
                    record_timestamp read from raw — not by data_idx
  5. Ordered        record_timestamp runs newest to oldest with no exceptions
  6. Clock          the parsed local time matches the raw text, re-parsed by an
                    independent parser written here, not by _TIME_FORMATS
  7. Offset         local minus UTC is +3 (EAT) on every row
  8. Null island    0,0 and unparseable coordinates are excluded
  9. Pagination     limit/offset slices the ordered result, nothing else

Property 4 is the one that matters most. data_idx in Cassandra is not
sequential — the window probe saw 1639489407, 140724096, 1929986458 in
descending time order on real rows — so a reader that tiebreaks on it would
keep the wrong fix for a coordinate and raise no error.

Read-only.

Usage:
    python scripts/location_store_selfcheck.py --imei 867556044727322 --day 15-08-2025
    python scripts/location_store_selfcheck.py --imei 867556044727322 --day 01-09-2025
"""

import argparse
import sys
from datetime import datetime

sys.path.insert(0, '.')
from config import CASSANDRA_KEYSPACE, DB_LINK          # noqa: E402
from endpoints import location_store                    # noqa: E402

RAW = (
    "SELECT data_device_imei, data_longitude, data_latitude, speed_log, "
    "data_hdop, local_system_datestamp, local_system_timestamp, "
    "record_io_events_uid, geocoded_location, data_connected_satelites, "
    "batch_uid, data_idx, record_timestamp "
    "FROM dll_location_registry_by_record_ts "
    "WHERE data_device_imei = ? AND local_system_datestamp = ?"
)

PASS, FAIL = [], []


def ok(label, detail=''):
    PASS.append(label)
    print(f'   ok  {label}' + (f'  — {detail}' if detail else ''))


def bad(label, detail):
    FAIL.append(f'{label}: {detail}')
    print(f'   !!  {label}  — {detail}')


def independent_clock(text):
    """Parse 'hh:mm:ssAM' without location_store's format list.

    Deliberately naive and written from scratch: if this and _TIME_FORMATS
    disagree, one of them is wrong and that is worth knowing.
    """
    raw = str(text or '').strip().upper()
    half = None
    for suffix in ('AM', 'PM'):
        if raw.endswith(suffix):
            half = suffix
            raw = raw[:-len(suffix)].strip()
            break
    parts = raw.split(':')
    if len(parts) < 2:
        return None
    try:
        h, m = int(parts[0]), int(parts[1])
        s = int(float(parts[2])) if len(parts) > 2 else 0
    except ValueError:
        return None
    if half == 'PM' and h != 12:
        h += 12
    if half == 'AM' and h == 12:
        h = 0
    if not (0 <= h < 24 and 0 <= m < 60 and 0 <= s < 60):
        return None
    return h, m, s


def num(value):
    try:
        return float(str(value).replace(',', '').strip())
    except (TypeError, ValueError):
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--imei', required=True)
    ap.add_argument('--day', required=True, help='DD-MM-YYYY, a day with rows')
    args = ap.parse_args()
    imei = ''.join(str(args.imei).split())

    from flask import Flask
    app = Flask(__name__)
    app.config['db_link'] = DB_LINK
    with app.app_context():
        from endpoints.devices import get_cassandra_session
        session = get_cassandra_session()
        if session is None:
            print('!! no Cassandra session')
            return 1

        stmt = session.prepare(RAW)
        raw = list(session.execute(stmt, (imei, args.day)))
        print(f'unit {imei}, day {args.day}')
        print(f'raw rows in Cassandra : {len(raw)}')
        if not raw:
            print('\n!! no rows for this unit on this day. Pick a day the')
            print('   window probe found — 15-08-2025 or 01-09-2025.')
            return 1

        try:
            fixes, truncated = location_store.fixes(
                session, imei, args.day, args.day)
        except location_store.PositionsUnavailable as error:
            print(f'\n!! the reader raised PositionsUnavailable: {error}')
            return 1
        print(f'fixes returned        : {len(fixes)}'
              + ('  [truncated]' if truncated else ''))

    # ── what the raw rows say, computed here, from them ─────────────────────
    valid = []
    nulls = 0
    for r in raw:
        lon, lat = num(r.data_longitude), num(r.data_latitude)
        if lon is None or lat is None or (lon == 0 and lat == 0):
            nulls += 1
            continue
        valid.append((lon, lat, r))
    coords = {}
    for lon, lat, r in valid:
        key = (lon, lat)
        best = coords.get(key)
        if best is None or (r.record_timestamp or datetime.min) > \
                (best.record_timestamp or datetime.min):
            coords[key] = r
    print(f'raw: {len(valid)} valid, {nulls} excluded, '
          f'{len(coords)} distinct coordinate(s)\n')

    returned = {(f['lon'], f['lat']) for f in fixes}

    print('=' * 68)
    print('PROPERTIES')
    print('=' * 68)

    # 1. no invention
    raw_keys = {(lon, lat) for lon, lat, _ in valid}
    invented = returned - raw_keys
    if invented:
        bad('1. no invention', f'{len(invented)} fix(es) not in raw, '
                              f'e.g. {sorted(invented)[:2]}')
    else:
        ok('1. no invention', 'every fix exists in the raw rows')

    # 2. no loss
    lost = set(coords) - returned
    if lost:
        bad('2. no loss', f'{len(lost)} distinct coordinate(s) dropped, '
                          f'e.g. {sorted(lost)[:2]}')
    else:
        ok('2. no loss', f'all {len(coords)} distinct coordinates returned')

    # 3. dedupe exact
    if len(fixes) != len(coords):
        bad('3. dedupe exact', f'{len(fixes)} rows for {len(coords)} '
                               f'distinct coordinates')
    else:
        ok('3. dedupe exact', 'one row per distinct coordinate')

    # 4. latest wins, by record_timestamp
    wrong = []
    for f in fixes:
        want = coords.get((f['lon'], f['lat']))
        if want is None:
            continue
        if f['at_utc'] != want.record_timestamp:
            wrong.append((f['lon'], f['lat'], f['at_utc'],
                          want.record_timestamp))
    if wrong:
        lon, lat, got, want = wrong[0]
        bad('4. latest wins', f'{len(wrong)} coordinate(s) kept the wrong row; '
                              f'at ({lon}, {lat}) kept {got}, newest is {want}')
    else:
        ok('4. latest wins', 'each coordinate kept its newest fix')

    # 5. ordering
    stamps = [f['at_utc'] for f in fixes if f['at_utc'] is not None]
    breaks = sum(1 for a, b in zip(stamps, stamps[1:]) if a < b)
    if breaks:
        bad('5. ordered', f'{breaks} place(s) where the order rises')
    else:
        ok('5. ordered', f'{len(stamps)} stamps, newest first, no breaks')

    # 6. clock, independently parsed
    clock_bad = []
    for f in fixes:
        want = independent_clock(f['timestamp'])
        if want is None or f['at'] is None:
            continue
        got = (f['at'].hour, f['at'].minute, f['at'].second)
        if got != want:
            clock_bad.append((f['timestamp'], got, want))
    if clock_bad:
        text, got, want = clock_bad[0]
        bad('6. clock', f'{len(clock_bad)} disagreement(s); {text!r} parsed '
                        f'as {got}, independently {want}')
    else:
        ok('6. clock', f'{len(fixes)} local times agree with an independent '
                       f'parser')

    # 7. offset
    offsets = {}
    for f in fixes:
        if f['at'] and f['at_utc']:
            delta = f['at'] - f['at_utc'].replace(tzinfo=None)
            offsets[round(delta.total_seconds() / 3600.0, 2)] = \
                offsets.get(round(delta.total_seconds() / 3600.0, 2), 0) + 1
    if offsets and set(offsets) == {3.0}:
        ok('7. offset', 'local is UTC+3 (EAT) on every row')
    elif offsets:
        bad('7. offset', f'mixed offsets: {offsets}')
    else:
        bad('7. offset', 'no row had both a local and a UTC stamp')

    # 8. null island
    if any((f['lon'], f['lat']) == (0, 0) for f in fixes):
        bad('8. null island', '0,0 present in the result')
    else:
        ok('8. null island', f'{nulls} unusable raw row(s) excluded')

    # 9. pagination
    if len(fixes) >= 6:
        with_app(args, imei, fixes)
    else:
        ok('9. pagination', 'skipped, too few rows to slice')

    print('\n' + '=' * 68)
    print(f'{len(PASS)} passed, {len(FAIL)} failed')
    if FAIL:
        print('\n   The reader is wrong. Do NOT switch any route:')
        for f in FAIL:
            print(f'     - {f}')
        return 1
    print('\n   The reader reports the store faithfully: nothing invented,')
    print('   nothing lost, deduped exactly, ordered by the one column that')
    print('   is reliably ordered, and the clock read correctly.')
    print('\n   This replaces B1, which cannot run — the stores do not share')
    print('   a single day.')
    print('\n   These properties prove the reader matches its specification.')
    print('   They say nothing about whether the specification is right, and')
    print('   it is not: the inherited coordinate dedupe reports GPS drift as')
    print('   history (390 "positions" for a van parked nine days) and cannot')
    print('   express dwell time at all. That is ticket B4 — consecutive')
    print('   speed==0 fixes become one stop with arrival, departure and')
    print('   duration. It does not block B2, which keeps the legacy')
    print('   semantics so the source change is the only variable.')
    return 0


def with_app(args, imei, full):
    """limit/offset must slice the ordered result and change nothing else."""
    from flask import Flask
    app = Flask(__name__)
    app.config['db_link'] = DB_LINK
    with app.app_context():
        from endpoints.devices import get_cassandra_session
        session = get_cassandra_session()
        page, _ = location_store.fixes(session, imei, args.day, args.day,
                                       limit=3, offset=2)
    want = [(f['lon'], f['lat']) for f in full[2:5]]
    got = [(f['lon'], f['lat']) for f in page]
    if got != want:
        bad('9. pagination', f'offset 2 limit 3 gave {got}, expected {want}')
    elif [f['row_index'] for f in page] != [1, 2, 3]:
        bad('9. pagination', f'row_index is '
                             f'{[f["row_index"] for f in page]}, expected [1, 2, 3]')
    else:
        ok('9. pagination', 'offset 2 limit 3 is the ordered slice, '
                            'row_index restarts at 1')


if __name__ == '__main__':
    sys.exit(main())
