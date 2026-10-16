"""
io_events_store.py — one place that reads IO events, from the live store.

Why this exists
---------------
trips_history read IO events from Postgres dll_io_events_executed_logs. That
table holds 55 million rows across 11 GB, has no index on
io_parent_io_event_uid, and — measured against both an old day and a recent
one — contains NONE of the uids these fixes reference: 0 of 10 recent, 0 of 3
old. So every lookup was a parallel sequential scan discarding ~19.7 million
rows per worker, 2.9 seconds each, to return nothing.

Cassandra holds the same table with io_parent_io_event_uid AS THE PARTITION
KEY, which makes each lookup a point read. The route's gate was
`if(cursor.rowcount >= 1)`, so it was always false, and everything behind it
never ran: the IO-name lookups and all four Config_Sources calls that produce
ignition, mileage, fuel and driver ID. Those read Cassandra and work.

Four things that do NOT port across, each of which would be silently wrong
-------------------------------------------------------------------------
1. ORDER BY data_idx. It is `integer` in Postgres and `text` in Cassandra, and
   the table has no clustering column, so Cassandra returns rows unordered.
   Sorted as text, real values order
       968159659, 809268972, ..., 2015440768, 1977860551
   instead of 2015440768 first. Ordering is done here, numerically.

2. ONE ROUND TRIP PER FIX. A point read costs 0.30s against the Kampala host,
   flat across ten consecutive runs, so it is latency and not query cost. Done
   serially a 500-fix page would spend 151 seconds waiting. The lookups are
   issued concurrently, so N fixes cost about one round trip.

3. THE VENDOR BRANCH. The route built the name-table key only for 'ruptela'
   and 'teltonika'. The test unit is 'xirgo_global', so IO_ID_Found was never
   assigned and opening the gate would have raised NameError on the first fix.
   vendor_io_id below handles every vendor.

4. THE NAME LOOKUP. dll_io_events_config currently holds ZERO rows, so no
   channel id resolves. The old code did `cursor.fetchone()[0]`, which is a
   TypeError on None. names_for returns a dict and the caller falls back to
   the raw channel id, so an empty reference table degrades the labels
   instead of taking the route down.

Failure is not emptiness
------------------------
IoEventsUnavailable is raised when the store cannot be read, rather than
returning {}. "We could not look" must never render as "this fix had no IO
events" — the distinction FleetUnavailable and PositionsUnavailable exist to
protect.
"""

TABLE = 'dll_io_events_executed_logs'

# Each entry is one point read on the partition key. The driver fans these out
# over the connection pool, so the wall time is roughly one round trip rather
# than N. Kept modest so a 15,000-row page cannot swamp the pool.
CONCURRENCY = 32


class IoEventsUnavailable(Exception):
    """The IO-event store could not be read."""


def _as_number(value):
    """data_idx as a sort key. It is text in Cassandra, so '9' must not sort
    above '10'.

    The tuple's first element keeps unparseable values LAST. Callers sort
    with reverse=True, so the largest key comes first, which means the
    sentinel has to be SMALLER than any real value — -1, not 1. Getting that
    backwards puts 'NoData' at the top of a fix's IO events, which is how the
    first version of this function behaved until a test said so.
    """
    try:
        return (0, int(str(value).strip()))
    except (TypeError, ValueError):
        return (-1, 0)


def vendor_io_id(vendor, event_uid):
    """The key the vendor's name table is indexed by.

    Ruptela ids carry a '.0' suffix in dll_io_events_config. Teltonika ids do
    not. Every other vendor — xirgo_global among them — uses the id as it
    comes, which is what the route failed to do: it assigned nothing at all
    and raised NameError.
    """
    uid = str(event_uid or '').strip()
    if str(vendor or '').strip().lower() == 'ruptela':
        return uid + '.0'
    return uid


def events_for(session, uids):
    """IO events for many fixes at once: {uid: [event, ...]}.

    Each event is a dict with 'event_uid', 'value' and 'data_idx', ordered
    newest first by data_idx as a NUMBER. A uid with no events maps to an
    empty list, so the caller can tell "looked, found none" from "never
    looked" — a uid absent from the dict was never asked about.

    Raises IoEventsUnavailable if the store cannot be read, or if any
    individual lookup fails: a partial answer here would look like a quiet
    fix with less telemetry than it really had.
    """
    if session is None:
        raise IoEventsUnavailable('no Cassandra session')

    wanted = []
    for uid in uids or ():
        text = str(uid or '').strip()
        if text and text not in wanted:
            wanted.append(text)
    if not wanted:
        return {}

    try:
        from cassandra.concurrent import execute_concurrent_with_args
    except Exception as error:      # noqa: BLE001
        raise IoEventsUnavailable(
            f'cassandra.concurrent unavailable: {error}') from error

    try:
        statement = session.prepare(
            f"SELECT io_parent_io_event_uid, event_uid_executed, "
            f"event_value_executed, data_idx FROM {TABLE} "
            f"WHERE io_parent_io_event_uid = ?")
    except Exception as error:      # noqa: BLE001
        raise IoEventsUnavailable(str(error)) from error

    try:
        outcomes = execute_concurrent_with_args(
            session, statement, [(uid,) for uid in wanted],
            concurrency=CONCURRENCY, raise_on_first_error=False)
    except Exception as error:      # noqa: BLE001
        raise IoEventsUnavailable(str(error)) from error

    found = {uid: [] for uid in wanted}
    for uid, outcome in zip(wanted, outcomes):
        ok, result = outcome
        if not ok:
            raise IoEventsUnavailable(f'{uid}: {result}')
        for row in result:
            found[uid].append({
                'event_uid': getattr(row, 'event_uid_executed', None),
                'value': getattr(row, 'event_value_executed', None),
                'data_idx': getattr(row, 'data_idx', None),
            })

    for uid in found:
        found[uid].sort(key=lambda e: _as_number(e['data_idx']), reverse=True)
    return found


def names_for(cursor, table, value_column, key_column, keys):
    """{key: display name} for the vendor's channel ids, in one query.

    Returns a dict rather than raising on a miss. dll_io_events_config holds
    no rows at all today, so every id is a miss; the caller labels the event
    with the raw channel id instead, which is worse than a name and far
    better than a 500.

    table, value_column and key_column come from the route's own vendor
    mapping, never from user input.
    """
    unique = sorted({str(k) for k in (keys or ()) if str(k or '').strip()})
    if not unique or cursor is None:
        return {}
    try:
        cursor.execute(
            f"SELECT {key_column}, {value_column} FROM {table} "
            f"WHERE {key_column} = ANY(%s)", (unique,))
        rows = cursor.fetchall() if cursor.rowcount > 0 else []
    except Exception:               # noqa: BLE001
        # A missing or empty reference table must not fail the request; the
        # caller degrades to raw ids.
        return {}
    return {str(key): value for key, value in rows if value is not None}
