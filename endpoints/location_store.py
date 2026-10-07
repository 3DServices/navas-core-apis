"""
location_store.py — one place that reads vehicle positions, from the live store.

Why this exists
---------------
Positions live in Cassandra. The Postgres copy of dll_location_registry holds
2,027,738 rows and its newest is dated 06-08-2025: the device listener stopped
writing there and kept writing to Cassandra. Everything in data.py still reads
the Postgres copy, which is why trip history and replay return nothing for any
recent date, and why unit 350317173603857 has 194 recorded trips and not one
Postgres position row.

Six queries across four routes (trips/excel, trips/pdf, trips/history,
trips/history/replay) each build the same SQL by hand. They are replaced by this
module so the source is decided once.

Two things that do NOT port across, and would be silently wrong if they did
-------------------------------------------------------------------------
1. ORDER BY data_idx. In Postgres data_idx was a serial, so "newest first" and
   "highest data_idx first" were the same statement. In Cassandra it is not
   sequential — three consecutive fixes from one unit carried 741899120,
   1645805121 and 1737047314 in descending time order. Ordering by it would
   shuffle the history and raise no error. Ordering here is by record_timestamp,
   which is the clustering column and an actual timestamp.

2. The window function. PARTITION BY data_longitude, data_latitude ... row_num=1
   kept one row per distinct coordinate, the latest. Cassandra has no window
   functions, so that is done here in Python, with record_timestamp as the
   tiebreak rather than data_idx for the reason above.

Times
-----
record_timestamp is UTC. local_system_datestamp / local_system_timestamp are
local (EAT, +3), which is what every caller renders and what a customer checks
against their own afternoon. Both are returned; the local pair is the one to
display.

Cost
----
The partition key is (data_device_imei, local_system_datestamp), so a range is
one query per day. A year would be 365 round trips, so the span is capped and
the result says when it was cut rather than quietly returning less.
"""

from datetime import datetime, timedelta

# A quarter is more than any report asks for interactively, and 92 queries is a
# cost a caller can see coming. Beyond it the answer says it was truncated.
MAX_DAYS = 92

# Backstop for a caller that passes no limit. With a limit the read stops as
# soon as the page is full, so this guards only the unbounded case. The busiest
# unit measured writes 13,407 fixes a day, so a quarter of them is 1.2 million
# dicts — enough to take a worker down on one customer's report.
MAX_ROWS = 400000

_DATE_FORMATS = ('%d-%m-%Y', '%Y-%m-%d', '%d/%m/%Y', '%Y/%m/%d')
_TIME_FORMATS = ('%I:%M:%S%p', '%I:%M:%S %p', '%I:%M%p', '%I:%M %p',
                 '%H:%M:%S', '%H:%M:%S.%f', '%H:%M')

_COLUMNS = (
    "data_device_imei, data_longitude, data_latitude, speed_log, data_hdop, "
    "local_system_datestamp, local_system_timestamp, record_io_events_uid, "
    "geocoded_location, data_connected_satelites, batch_uid, data_idx, "
    "record_timestamp"
)


class PositionsUnavailable(Exception):
    """The position store could not be read.

    Raised rather than returning an empty list, so that "we could not look" is
    never mistaken for "this vehicle did not move" — the same distinction
    waswa_fleet.FleetUnavailable exists to protect.
    """


def _as_date(text):
    if hasattr(text, 'year') and not hasattr(text, 'hour'):
        return text
    if hasattr(text, 'date'):
        return text.date()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(str(text).strip(), fmt).date()
        except (ValueError, TypeError):
            continue
    return None


def _as_time(text):
    value = str(text or '').strip()
    if not value:
        return None
    for fmt in _TIME_FORMATS:
        try:
            return datetime.strptime(value, fmt).time()
        except ValueError:
            continue
    return None


def _stamp(datestamp, timestamp):
    """Local datetime from the text pair, or None. Never epoch: a zero date
    would become a fix from 1970 sitting at the top of a history."""
    day = _as_date(datestamp)
    if day is None:
        return None
    clock = _as_time(timestamp)
    return datetime.combine(day, clock or datetime.min.time())


def _num(value):
    try:
        return float(str(value).replace(',', '').strip())
    except (TypeError, ValueError):
        return None


def days_in(from_date, to_date):
    """The days to query, oldest first, as DD-MM-YYYY text.

    One day at a time, not a range: local_system_datestamp is part of the
    partition key AND it is text in DD-MM-YYYY, so '01-09-2026' sorts before
    '31-08-2026'. A CQL range over it returns the wrong rows and reports
    nothing wrong. Equality on an exact day is the only form that cannot lie.
    """
    start, end = _as_date(from_date), _as_date(to_date)
    if not start or not end:
        return [], False
    if end < start:
        start, end = end, start
    out, day = [], start
    while day <= end:
        if len(out) >= MAX_DAYS:
            return out, True
        out.append(day.strftime('%d-%m-%Y'))
        day += timedelta(days=1)
    return out, False


def _order_key(row):
    """record_timestamp first: it is the only reliably ordered value on these
    rows. data_idx is not sequential in Cassandra, and the local text pair is
    the fallback for a row whose record_timestamp is missing."""
    return (row['at_utc'] or row['at'] or datetime.min)


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


def _row(r, low, high, span_from=None, span_to=None):
    """One Cassandra row as a fix, or None when it is unusable or falls outside
    the clock window or the datetime span."""
    lon = _num(getattr(r, 'data_longitude', None))
    lat = _num(getattr(r, 'data_latitude', None))
    if lon is None or lat is None or (lon == 0 and lat == 0):
        return None
    at = _stamp(getattr(r, 'local_system_datestamp', None),
                getattr(r, 'local_system_timestamp', None))
    if (low or high) and at is not None:
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
    return {
        'imei': str(getattr(r, 'data_device_imei', '') or ''),
        'lon': lon,
        'lat': lat,
        'speed': getattr(r, 'speed_log', None),
        'hdop': getattr(r, 'data_hdop', None),
        'datestamp': getattr(r, 'local_system_datestamp', None),
        'timestamp': getattr(r, 'local_system_timestamp', None),
        'io_uid': getattr(r, 'record_io_events_uid', None),
        'place': getattr(r, 'geocoded_location', None),
        'satellites': getattr(r, 'data_connected_satelites', None),
        'batch_uid': getattr(r, 'batch_uid', None),
        'data_idx': getattr(r, 'data_idx', None),
        'at': at,
        'at_utc': getattr(r, 'record_timestamp', None),
    }


def fixes(session, imei, from_date, to_date,
          limit=None, offset=0, time_from=None, time_to=None,
          datetime_from=None, datetime_to=None,
          dedupe_coordinates=True, newest_first=True):
    """Position fixes for one unit, as a list of dicts.

    session               a Cassandra session (devices.get_cassandra_session())
    limit / offset        applied AFTER dedupe and ordering, as the SQL did
    time_from / time_to   optional clock window: these hours on EVERY day in
                          the range. NOT what the replay route wants --
                          see datetime_from below.
    datetime_from /       optional continuous span: one range from an instant
    datetime_to           to an instant, which is what a replay is. Naive
                          local datetimes; build them with local_datetime().
                          A fix whose local timestamp will not parse is
                          excluded from a span (but not from a clock window)
    dedupe_coordinates    keep one fix per distinct (lon, lat), the latest —
                          what PARTITION BY ... row_num = 1 did
    newest_first          the SQL ordered DESC; callers paginate on that

    Raises PositionsUnavailable when the store cannot be read, or when an
    unbounded request would materialise more than MAX_ROWS fixes.
    """
    if session is None:
        raise PositionsUnavailable('no Cassandra session')
    wanted = ''.join(str(imei or '').split())
    if not wanted:
        return [], False

    days, truncated = days_in(from_date, to_date)
    if not days:
        return [], False

    try:
        stmt = session.prepare(
            f"SELECT {_COLUMNS} FROM dll_location_registry_by_record_ts "
            f"WHERE data_device_imei = ? AND local_system_datestamp = ?")
    except Exception as error:      # noqa: BLE001
        raise PositionsUnavailable(str(error)) from error

    low, high = _as_time(time_from), _as_time(time_to)

    # When the caller wants a page of the NEWEST fixes — which every route in
    # data.py does — the days can be read newest first and the read stopped the
    # moment the page is full. The busiest unit writes 13,407 fixes a day, so
    # reading a 92-day span to return 15,000 rows means a million dicts in a
    # worker to serve a page that needs one or two days.
    #
    # Why first-seen-wins is exact here and not an approximation:
    # local_system_datestamp is the LOCAL date while record_timestamp is UTC,
    # and EAT is a fixed +3, so local day D occupies UTC [D-1 21:00, D 21:00).
    # Consecutive local days therefore sit in adjacent, non-overlapping UTC
    # ranges. Walking days newest first, and rows newest first within a day,
    # visits fixes in strictly descending time order — so the first time a
    # coordinate is seen IS its latest occurrence, which is the row the dedupe
    # keeps, and the first offset+limit coordinates seen are exactly the page.
    #
    # This is not available for newest_first=False: walking oldest first makes
    # first-seen the EARLIEST occurrence, while the dedupe keeps the latest.
    page = None
    if limit is not None and newest_first:
        page = max(0, int(offset or 0)) + max(0, int(limit))

    kept, sequence, enough = {}, [], False
    for day in (list(reversed(days)) if page is not None else days):
        try:
            found = session.execute(stmt, (wanted, day))
        except Exception as error:  # noqa: BLE001
            raise PositionsUnavailable(f'{day}: {error}') from error

        day_rows = [row for row in (_row(r, low, high, datetime_from,
                                          datetime_to) for r in found)
                    if row is not None]

        if page is None:
            sequence.extend(day_rows)
            if len(sequence) > MAX_ROWS:
                raise PositionsUnavailable(
                    f'{from_date} to {to_date} holds more than {MAX_ROWS} '
                    f'fixes for {wanted}; ask for a shorter range or pass a '
                    f'limit')
            continue

        day_rows.sort(key=_order_key, reverse=True)
        for row in day_rows:
            if dedupe_coordinates:
                key = (row['lon'], row['lat'])
                if key not in kept:
                    kept[key] = row
                enough = len(kept) >= page
            else:
                sequence.append(row)
                enough = len(sequence) >= page
            if enough:
                break
        if enough:
            break

    if page is not None:
        rows = list(kept.values()) if dedupe_coordinates else sequence
    else:
        rows = sequence
        if dedupe_coordinates:
            best = {}
            for row in rows:
                key = (row['lon'], row['lat'])
                if key not in best or _order_key(row) > _order_key(best[key]):
                    best[key] = row
            rows = list(best.values())

    rows.sort(key=_order_key, reverse=newest_first)

    start = max(0, int(offset or 0))
    if limit is not None:
        rows = rows[start:start + max(0, int(limit))]
    elif start:
        rows = rows[start:]

    for index, row in enumerate(rows, 1):
        row['row_index'] = index
    return rows, truncated


# ── Tuple shapes the existing callers unpack ────────────────────────────────
# data.py indexes these positionally, so the orders below are the contract and
# must not be reordered. Returning tuples keeps those routes unchanged.

def as_history_tuple(row):
    """trips/excel, trips/pdf, trips/history, trips/history/replay (main query).

    0 lon  1 lat  2 speed  3 hdop  4 datestamp  5 io_uid  6 place
    7 timestamp  8 satellites  9 batch_uid  10 data_idx  11 row_index
    """
    return (row['lon'], row['lat'], row['speed'], row['hdop'],
            row['datestamp'], row['io_uid'], row['place'], row['timestamp'],
            row['satellites'], row['batch_uid'], row['data_idx'],
            row['row_index'])


def as_replay_tuple(row):
    """trips/history/replay, the per-device summary query.

    0 imei  1 place  2 lon  3 lat  4 speed  5 datestamp  6 timestamp
    7 satellites
    """
    return (row['imei'], row['place'], row['lon'], row['lat'], row['speed'],
            row['datestamp'], row['timestamp'], row['satellites'])
