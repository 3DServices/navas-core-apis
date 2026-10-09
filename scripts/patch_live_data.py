#!/usr/bin/env python3
"""Point waswa_fleet at the data that is actually being written.

The schema probe settled four things, two of which are traps that produce wrong
answers rather than errors:

  dll_location_registry_by_record_ts
      PARTITION KEY : data_device_imei (text), local_system_datestamp (text)
      CLUSTERING    : record_timestamp (timestamp), local_system_timestamp (text)
      speed_log int, geocoded_location text, data_latitude/longitude double

  1. The partition key is COMPOSITE. Restricting only the IMEI is refused
     outright — which is why my own sample query failed. Every read must name a
     day as well, so the natural unit of work is one day at a time.

  2. local_system_datestamp is TEXT in DD-MM-YYYY, and it is part of the key.
     '01-09-2026' sorts BEFORE '31-08-2026' as a string, so a CQL range over it
     returns the wrong rows and reports no error at all. Only equality on an
     exact day is safe. This is the trap: a range query here would have looked
     like it worked.

  3. record_timestamp is UTC; local_system_timestamp is local. The sample makes
     it plain — record_timestamp 09:42:39 against local 12:42:39PM, the three
     hours being EAT. Reporting the UTC value as the time a vehicle passed
     somewhere would be wrong by three hours, every time, invisibly.

  4. speed_log exists, so "and it was fast" is answerable; geocoded_location is
     populated, but with administrative places ("Namilyango-kisenyi, Mukono,
     Central Region, Uganda") rather than points of interest, so it gives free
     context and does not answer "a mosque".

What this changes:

  _points         -> Cassandra, one day per query, local time for display.
  unit_trips      -> dll_trips_auditor, the table the console's Trips report
                     reads, instead of recomputing trips from raw fixes with
                     waswa_fleet's own private definition of a trip.
  fleet_activity  -> the same table, aggregated.
  unit_status     -> gains the last known position and whether the unit is on a
                     trip right now, which is what "where is my vehicle" needs.

unit_route_probe is left alone: it already filters by speed before thinning, so
it starts working the moment _points returns live data.

Idempotent.
"""
import ast
import io
import sys

PATH = 'endpoints/waswa_fleet.py'

HELPERS = '''
# Cassandra partitions positions by day, so a long range is many queries. A
# month is plenty for any question a person asks in a chat, and the cap is what
# stops "show me this year" from becoming 365 round trips.
_MAX_DAYS = 31


def _as_date(text):
    """A date from DD-MM-YYYY (or the other shapes _stamp knows), or None."""
    if hasattr(text, 'year') and hasattr(text, 'month'):
        return text.date() if hasattr(text, 'hour') else text
    stamped = _stamp(text, '00:00:00')
    return stamped.date() if stamped else None


def _days(from_date, to_date):
    """Every day in the range, oldest first, as DD-MM-YYYY text.

    Walked one day at a time, not expressed as a range, and that is deliberate.
    local_system_datestamp is part of the partition key AND it is text in
    DD-MM-YYYY, so '01-09-2026' < '31-08-2026' lexicographically. A CQL range
    over it would quietly return the wrong rows. Equality on one day is the
    only form that cannot be silently wrong.
    """
    start, end = _as_date(from_date), _as_date(to_date)
    if not start or not end:
        return []
    if end < start:
        start, end = end, start
    out, day = [], start
    while day <= end and len(out) < _MAX_DAYS:
        out.append(day.strftime('%d-%m-%Y'))
        day += timedelta(days=1)
    return out


def _clock(text):
    """A time string only if it really is one. end_time holds 'Incoming' while
    a trip is still running, and reporting that as a time would be nonsense."""
    value = str(text or '').strip()
    return value if ':' in value else None


def _trip_rows(cur, imeis, start, end):
    """Recorded trips for these units, newest first.

    dll_trips_auditor is where trips live now, and where the console's Trips
    report reads them. trip_date is a real date column, so this range is an
    ordinary BETWEEN with no text-sorting to worry about.
    """
    cur.execute("""
        SELECT device_imei, trip_uid, trip_date, start_time, end_time,
               start_mileage, end_mileage, start_fuel_level, end_fuel_level,
               driver_id, starting_location_point, end_location_point,
               trip_status
          FROM dll_trips_auditor
         WHERE device_imei = ANY(%s) AND trip_date BETWEEN %s AND %s
         ORDER BY trip_date DESC, id DESC""", (list(imeis), start, end))
    return cur.fetchall() if cur.rowcount > 0 else []


def _trip(row):
    """One recorded trip, in the shape Waswa should say out loud.

    Distance comes from the odometer readings, not from adding up straight lines
    between fixes: the odometer is what the vehicle itself measured, and it is
    what the Trips report quotes. When either reading is missing the distance is
    None, never 0 — a trip of unknown length is not a trip of no length.
    """
    (_imei, uid, date, t0, t1, m0, m1, f0, f1, driver,
     loc0, loc1, status) = row

    state = str(status or '').strip()
    ended = state.lower() == 'ended' and _clock(t1) is not None

    km = None
    a, b = _num(m0), _num(m1)
    if a is not None and b is not None and b >= a:
        km = round(b - a, 2)

    out = {
        'trip_uid': str(uid) if uid else None,
        'date': date.isoformat() if hasattr(date, 'isoformat') else str(date),
        'started': _clock(t0),
        'ended': _clock(t1) if ended else None,
        'in_progress': not ended,
        'distance_km': km,
        'from': str(loc0 or '').strip() or None,
        'to': (str(loc1 or '').strip() or None) if ended else None,
        'status': state or None,
    }
    fuel0, fuel1 = _num(f0), _num(f1)
    if fuel0 is not None and fuel1 is not None and fuel0 >= fuel1:
        out['fuel_used'] = round(fuel0 - fuel1, 2)
    if driver:
        out['driver_id'] = str(driver)
    return out
'''

POINTS = '''def _points(imei, from_date, to_date, limit=_MAX_POINTS):
    """Position fixes from the LIVE store, oldest first.

    Cassandra navas_iot_dbx.dll_location_registry_by_record_ts — NOT the
    Postgres table of the same name, which holds two million rows and stopped
    taking new ones on 06-08-2025 while the device listener carried on writing
    here. Unit 350317173603857 has 194 recorded trips and not one Postgres
    position row, which is how that was finally noticed.

    One query per day, because the partition key is
    (data_device_imei, local_system_datestamp) and both parts must be named.
    See _days for why a range over that text date would be silently wrong.

    'at' is the LOCAL time. record_timestamp is UTC and three hours behind it;
    a customer checking "when did it pass there" against their own afternoon
    needs the clock they live in. When the local time cannot be read, 'at' is
    None rather than the UTC value, because a time that is quietly three hours
    out is worse than a missing one.
    """
    days = _days(from_date, to_date)
    if not days:
        return []

    try:
        session = _cassandra()
    except Exception as error:      # noqa: BLE001
        raise FleetUnavailable(str(error)) from error
    if session is None:
        raise FleetUnavailable('no Cassandra session')

    try:
        stmt = session.prepare(
            "SELECT data_latitude, data_longitude, speed_log, geocoded_location, "
            "       record_timestamp, local_system_datestamp, "
            "       local_system_timestamp "
            "FROM dll_location_registry_by_record_ts "
            "WHERE data_device_imei = ? AND local_system_datestamp = ?")
    except Exception as error:      # noqa: BLE001
        raise FleetUnavailable(str(error)) from error

    wanted = re.sub(r'\\s+', '', str(imei or ''))
    out = []
    for day in days:
        if len(out) >= limit:
            break
        try:
            rows = session.execute(stmt, (wanted, day))
        except Exception as error:      # noqa: BLE001
            raise FleetUnavailable(f'positions for {day}: {error}') from error
        for r in rows:
            la = _num(getattr(r, 'data_latitude', None))
            lo = _num(getattr(r, 'data_longitude', None))
            if la is None or lo is None or (la == 0 and lo == 0):
                continue
            out.append({
                'lat': la,
                'lon': lo,
                'speed': _num(getattr(r, 'speed_log', None)) or 0.0,
                'at': _stamp(getattr(r, 'local_system_datestamp', None),
                             getattr(r, 'local_system_timestamp', None)),
                'place': str(getattr(r, 'geocoded_location', '') or '').strip(),
            })
            if len(out) >= limit:
                break
    return out
'''

TRIPS = '''def unit_trips(imei=None, from_date=None, to_date=None, client_uid=None,
               scope=None):
    """Trips for a unit, as the platform recorded them.

    Reads dll_trips_auditor, which is what the console's Trips report reads.
    This used to recompute trips from raw fixes using waswa_fleet's own private
    notion of where one trip ends (_TRIP_GAP_MINUTES, _MOVING_SPEED) — so Waswa
    and the Trips report could hand the same customer different trip counts for
    the same day. A customer who finds that contradiction believes neither
    number again, which is a worse outcome than a missing answer, so both now
    come from one place.
    """
    unit = _owned(imei, scope, client_uid)
    if not unit:
        return {'found': False, 'reason': 'no such unit on this account'}
    start, end = _as_date(from_date), _as_date(to_date)
    if not start or not end:
        return {'found': False,
                'reason': 'a date range is required, as DD-MM-YYYY'}
    if end < start:
        start, end = end, start

    conn = _pg()
    try:
        with conn.cursor() as cur:
            rows = _trip_rows(cur, [unit['imei']], start, end)
    except psycopg2.Error as error:
        raise FleetUnavailable(f'trip records could not be read: {error}')
    finally:
        conn.close()

    trips = [_trip(r) for r in rows]
    measured = [t['distance_km'] for t in trips if t['distance_km'] is not None]
    running = [t for t in trips if t['in_progress']]
    return {
        'found': bool(trips),
        'imei': unit['imei'],
        'name': unit['name'],
        'from': start.isoformat(), 'to': end.isoformat(),
        'trip_count': len(trips),
        'on_a_trip_now': bool(running),
        'total_distance_km': round(sum(measured), 2) if measured else None,
        'distance_source': ('odometer readings' if measured
                            else 'no odometer readings on these trips'),
        'trips': trips[:40],
        'truncated': len(trips) > 40,
        'reason': None if trips else 'no trips are recorded for this unit in '
                                    'that range',
    }
'''

ACTIVITY = '''def fleet_activity(days=None, client_uid=None, scope=None):
    """What the account's fleet did lately, from the recorded trips.

    Same source as unit_trips and the Trips report. A unit with trips but no
    odometer readings is counted as having moved and contributes no distance,
    which is reported rather than smoothed over: a fleet total that silently
    omits some units is the kind of number someone makes a decision on.
    """
    target = _target_client(scope, client_uid)
    if not target:
        return {'found': False,
                'reason': 'no client named — ask which client this is about'}
    units = _units_of(target)
    if not units:
        return {'found': False,
                'reason': 'no units are registered to this account'}

    span = max(1, min(int(_num(days) or 2), _MAX_DAYS))
    end = datetime.now().date()
    start = end - timedelta(days=span - 1)

    known = {u['imei']: u for u in units if u['imei']}
    conn = _pg()
    try:
        with conn.cursor() as cur:
            rows = _trip_rows(cur, list(known), start, end)
    except psycopg2.Error as error:
        raise FleetUnavailable(f'trip records could not be read: {error}')
    finally:
        conn.close()

    tally = {imei: {'trips': 0, 'km': 0.0, 'measured': 0,
                    'last': None, 'running': False} for imei in known}
    for row in rows:
        slot = tally.get(str(row[0] or ''))
        if slot is None:
            continue
        trip = _trip(row)
        slot['trips'] += 1
        if trip['distance_km'] is not None:
            slot['km'] += trip['distance_km']
            slot['measured'] += 1
        slot['running'] = slot['running'] or trip['in_progress']
        if slot['last'] is None or trip['date'] > slot['last']:
            slot['last'] = trip['date']

    listed = [{
        'imei': imei,
        'name': known[imei]['name'],
        'trips': slot['trips'],
        'distance_km': round(slot['km'], 2) if slot['measured'] else None,
        'last_trip': slot['last'],
        'on_a_trip_now': True if slot['running'] else None,
    } for imei, slot in tally.items()]
    listed.sort(key=lambda s: (-s['trips'], s['name'] or ''))

    moved = [s for s in listed if s['trips']]
    unmeasured = [s for s in moved if s['distance_km'] is None]
    total = sum(s['distance_km'] or 0.0 for s in listed)
    note = None
    if unmeasured:
        note = (f'{len(unmeasured)} unit(s) made trips with no odometer '
                f'readings, so the distance total does not include them')
    return {
        'found': True,
        'days': span,
        'from': start.isoformat(), 'to': end.isoformat(),
        'units_considered': len(listed),
        'units_that_moved': len(moved),
        'units_on_a_trip_now': sum(1 for s in listed if s['on_a_trip_now']),
        'total_distance_km': round(total, 2) if total else None,
        'units': listed[:40],
        'note': note,
    }
'''

STATUS = '''def unit_status(imei=None, client_uid=None, scope=None):
    """Why a unit is or is not reporting, and where it was last — facts only.

    "Where is my vehicle" was the question Waswa could never answer, so the
    last known position is part of the answer now, read from the live Cassandra
    store. The position is fetched from the heartbeat's own day, which is both
    the right partition to ask for and the only day that can hold the latest
    fix.
    """
    unit = _owned(imei, scope, client_uid)
    if not unit:
        return {'found': False, 'reason': 'no such unit on this account'}

    status = {'found': True, 'imei': unit['imei'], 'name': unit['name'],
              'vehicle': ' '.join(x for x in (unit['make'], unit['model']) if x),
              'billing_status': unit['billing_status'] or 'unrecorded'}

    session = None
    try:
        session = _cassandra()
    except Exception:       # noqa: BLE001
        session = None
    if session is None:
        status['heartbeat'] = 'the unit registry could not be reached'
    else:
        seen = None
        day_text = None
        try:
            stmt = session.prepare(
                "SELECT last_heartbeat_date, last_heartbeat_time "
                "FROM dll_pulse_status_registry WHERE device_data_imei = ? "
                "LIMIT 1")
            row = session.execute(stmt, (unit['imei'],)).one()
        except Exception:       # noqa: BLE001
            row = None
            status['heartbeat'] = 'the heartbeat record could not be read'
        if row is None:
            status.setdefault('heartbeat', 'this unit has never reported')
            status['last_reported_at'] = None
        else:
            day_text = getattr(row, 'last_heartbeat_date', None)
            seen = _stamp(day_text, getattr(row, 'last_heartbeat_time', None))
            status['last_reported_at'] = seen.isoformat(sep=' ') if seen else None
            if seen:
                hours = (datetime.now() - seen).total_seconds() / 3600.0
                status['hours_since_last_report'] = round(hours, 1)
                status['reporting_today'] = seen.date() == datetime.now().date()
            else:
                status['heartbeat'] = (
                    f'a heartbeat is recorded but its timestamp could not be '
                    f'read ({day_text!r})')

        # The last fix, from the heartbeat's own day. Ordered DESC on the
        # clustering column, which is allowed because both parts of the
        # partition key are named.
        if day_text:
            try:
                last = session.prepare(
                    "SELECT data_latitude, data_longitude, speed_log, "
                    "       geocoded_location, local_system_datestamp, "
                    "       local_system_timestamp "
                    "FROM dll_location_registry_by_record_ts "
                    "WHERE data_device_imei = ? AND local_system_datestamp = ? "
                    "ORDER BY record_timestamp DESC LIMIT 1")
                fix = session.execute(last, (unit['imei'], str(day_text))).one()
            except Exception:       # noqa: BLE001
                fix = None
                status['last_position'] = 'the position store could not be read'
            if fix is not None:
                la = _num(getattr(fix, 'data_latitude', None))
                lo = _num(getattr(fix, 'data_longitude', None))
                at = _stamp(getattr(fix, 'local_system_datestamp', None),
                            getattr(fix, 'local_system_timestamp', None))
                if la is not None and lo is not None:
                    status['last_position'] = {
                        'lat': round(la, 6), 'lon': round(lo, 6),
                        'at': at.isoformat(sep=' ') if at else None,
                        'speed_kph': _num(getattr(fix, 'speed_log', None)) or 0,
                        'near': str(getattr(fix, 'geocoded_location', '')
                                    or '').strip() or None,
                    }

    conn = _pg()
    try:
        with conn.cursor() as cur:
            # target_uid, not target: pause.py owns this table and that is
            # what it calls the column. Scope is not filtered here on purpose —
            # a rule on the unit, its group or the account all leave the
            # vehicle dark, and the customer only wants to know that it is.
            cur.execute("SELECT mode, active FROM dll_pause_rules "
                        "WHERE target_uid = %s AND active = TRUE",
                        (unit['imei'],))
            rules = cur.fetchall() if cur.rowcount > 0 else []
            status['paused_by_rule'] = [r[0] for r in rules] or None

            # On a trip right now? end_time reads 'Incoming' while one runs.
            today = datetime.now().date()
            open_trips = [t for t in (_trip(r) for r in _trip_rows(
                cur, [unit['imei']], today - timedelta(days=1), today))
                if t['in_progress']]
            status['on_a_trip_now'] = bool(open_trips)
            if open_trips:
                status['current_trip'] = open_trips[0]
    except psycopg2.Error:
        status['paused_by_rule'] = 'pause rules could not be read'
    finally:
        conn.close()

    return status
'''


def replace(src, name, new_text):
    """Swap a top-level function for new source, located by AST rather than by
    matching text: these functions are long, and a near-miss on a text match
    would corrupt the module."""
    tree = ast.parse(src)
    found = [n for n in tree.body
             if isinstance(n, ast.FunctionDef) and n.name == name]
    if len(found) != 1:
        raise SystemExit(f'!! expected one {name}, found {len(found)}')
    node = found[0]
    lines = src.splitlines(keepends=True)
    head = ''.join(lines[:node.lineno - 1])
    tail = ''.join(lines[node.end_lineno:])
    if not new_text.endswith('\n'):
        new_text += '\n'
    return head + new_text + tail


def main():
    src = io.open(PATH, encoding='utf-8', newline='').read()
    if '_by_record_ts' in src:
        print('  already pointed at the live store')
        return 0

    # Helpers first, so the replaced functions can use them.
    at = src.find('def _points(')
    if at < 0:
        raise SystemExit('!! _points not found')
    src = src[:at] + HELPERS.strip('\n') + '\n\n\n' + src[at:]
    print('  added _MAX_DAYS, _as_date, _days, _clock, _trip_rows, _trip')

    for name, text in (('_points', POINTS), ('unit_status', STATUS),
                       ('unit_trips', TRIPS), ('fleet_activity', ACTIVITY)):
        src = replace(src, name, text)
        print(f'  rewrote {name}')

    ast.parse(src)
    io.open(PATH, 'w', encoding='utf-8', newline='').write(src)
    print(f'  written: {PATH}')
    print('  syntax OK')
    return 0


if __name__ == '__main__':
    sys.exit(main())
