"""
waswa_fleet.py — Waswa's tools for looking at units, trips and movement.

The product and knowledge tools answer "what does OLIWA do". These answer
"what did THIS vehicle actually do", which is the difference between Waswa
reciting the six usual reasons a tracker goes quiet and Waswa saying that
UBK 415K last reported forty-one hours ago with its subscription running and
no pause rule set.

THE SCOPING RULE, which matters more than anything else here
-----------------------------------------------------------
The model names a unit; the SERVER decides whose fleet it may look in. Every
function takes `scope`, built by assistant.py from the signed-in account and
never from the conversation. Anything the model passes for client_uid is
dropped for a customer — the same discipline waswa_knowledge applies to
`audience`. Without it, a customer types a competitor's plate and Waswa
answers, which is a data breach delivered conversationally.

A unit that is not in scope returns `found: false`. It never says "that unit
belongs to someone else", because confirming a plate exists is itself a leak.

WHAT IS COMPUTED HERE VERSUS WHAT THE MODEL SEES
------------------------------------------------
Raw telemetry never reaches the model. A day of driving is thousands of rows
in dll_location_registry; handing those over would blow the context window,
cost a fortune per question, and ask a language model to do arithmetic it is
bad at. Every tool here reduces first — segments trips, measures distances,
counts, filters — and returns findings with a small sample as evidence.

Sources, so the next person does not have to go looking:
    units               Cassandra dll_device_basic_data (device_client)
    heartbeat           Cassandra dll_pulse_status_registry
    billing status      dll_device_basic_data.device_billing_status
    pause rules         Postgres dll_pause_rules
    positions + speed   Postgres dll_location_registry
"""

import math
import re
from datetime import datetime, timedelta

import psycopg2
import requests
from flask import current_app

# ── Budgets ─────────────────────────────────────────────────────────────────
# A trip is thousands of GPS fixes and Places Nearby Search is billed per
# request, so an unbounded probe turns one customer question into a huge bill
# and several minutes of latency. The order matters: filter by the condition
# the user actually asked about, THEN thin what survives, THEN cap.
_MAX_PROBES = 25                 # Places calls per question, hard ceiling
_PROBE_SPACING_M = 250           # no two probes closer together than this
_PROBE_RADIUS_M = 300            # how far around a probe point to look
_MAX_POINTS = 20000              # rows read from dll_location_registry per call
_TRIP_GAP_MINUTES = 10           # silence this long ends a trip
_MOVING_SPEED = 5                # km/h below which a unit is treated as stopped
_PLACES_URL = 'https://maps.googleapis.com/maps/api/place/nearbysearch/json'
_PLACES_TIMEOUT = 6


# ── Scope ───────────────────────────────────────────────────────────────────

def build_scope(account_uid, client_uid, is_staff=False):
    """The only thing that decides whose data a tool may read."""
    return {'account_uid': str(account_uid or ''),
            'client_uid': str(client_uid or ''),
            'is_staff': bool(is_staff)}


def _target_client(scope, requested):
    """Which client's fleet this call may read.

    A customer is pinned to their own, whatever the model asked for. Staff may
    name one; without a name there is nothing to search, and saying so is
    better than silently searching every client on the platform.
    """
    own = (scope or {}).get('client_uid') or ''
    if not (scope or {}).get('is_staff'):
        return own or None
    named = str(requested or '').strip()
    return named or own or None


# ── Database ────────────────────────────────────────────────────────────────

class FleetUnavailable(Exception):
    """The vehicle register could not be read.

    Raised rather than returned, so that no caller can mistake it for an empty
    fleet by forgetting to check a flag. "I could not look" and "there is
    nothing there" are different answers to a customer, and only one of them is
    safe to guess at.
    """


def _warn(message, *args):
    """Fleet faults belong in the Flask log, not only in the chat window."""
    try:
        current_app.logger.warning('[waswa.fleet] ' + message, *args)
    except Exception:       # noqa: BLE001 - logging must never break a turn
        pass


def _pg():
    return psycopg2.connect(current_app.config['db_link'])


def _cassandra():
    from .devices import get_cassandra_session
    return get_cassandra_session()


def _units_of(client_uid):
    """Every unit registered to a client.

    Raises FleetUnavailable when the register cannot be read. It must not
    return [] for that: an empty list is indistinguishable from "this customer
    owns nothing", and Cassandra timing out is not evidence about what anybody
    owns.
    """
    if not client_uid:
        return []
    try:
        session = _cassandra()
    except Exception as error:      # noqa: BLE001
        raise FleetUnavailable(str(error)) from error
    if session is None:
        raise FleetUnavailable('no Cassandra session')
    try:
        stmt = session.prepare(
            "SELECT device_imei, device_name, device_car_make, device_car_model, "
            "device_vin_number, device_billing_status "
            "FROM dll_device_basic_data WHERE device_client = ? ALLOW FILTERING")
        rows = session.execute(stmt, (str(client_uid),))
    except Exception as error:      # noqa: BLE001
        raise FleetUnavailable(str(error)) from error
    out = []
    for r in rows:
        out.append({
            'imei': str(getattr(r, 'device_imei', '') or ''),
            'name': str(getattr(r, 'device_name', '') or ''),
            'make': str(getattr(r, 'device_car_make', '') or ''),
            'model': str(getattr(r, 'device_car_model', '') or ''),
            'vin': str(getattr(r, 'device_vin_number', '') or ''),
            'billing_status': str(getattr(r, 'device_billing_status', '') or ''),
        })
    return out


def _owned(imei, scope, client_uid=None):
    """The unit record, or None when it is not this caller's to see."""
    target = _target_client(scope, client_uid)
    if not target:
        return None
    wanted = re.sub(r'\s+', '', str(imei or ''))
    for unit in _units_of(target):
        if unit['imei'] == wanted:
            return unit
    return None


# ── Geometry ────────────────────────────────────────────────────────────────

def _metres(lat1, lon1, lat2, lon2):
    """Great-circle distance. Good to a metre or so at these scales."""
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = (math.sin(dp / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2)
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def _num(value):
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


# Dates arrive as text and not always in the same shape: dll_location_registry
# writes DD-MM-YYYY, dll_pulse_status_registry has been seen holding at least
# two others, and statistics.py has tried four formats against it for as long
# as it has existed. A parse failure here is silent and total — it empties the
# heartbeat, every trip and all of fleet activity at once — so try what the
# rest of the codebase already tries.
_DATE_FORMATS = ('%d-%m-%Y', '%Y-%m-%d', '%d/%m/%Y', '%Y/%m/%d')
# 12-hour first: dll_pulse_status_registry writes '08:25:50AM', with no
# space before the meridiem. %H would read '08' correctly and then choke
# on the 'AM', so the 24-hour patterns must not get first refusal on a
# string that ends in one.
_TIME_FORMATS = (
    '%I:%M:%S%p', '%I:%M:%S %p', '%I:%M%p', '%I:%M %p',
    '%H:%M:%S', '%H:%M:%S.%f', '%H:%M',
)


def _stamp(datestamp, timestamp):
    """A datetime from the text pair, or None if nothing reads it.

    None means "unknown", never "epoch": a zero date would quietly become a
    unit that last reported in 1970 and a trip 56 years long.
    """
    if datestamp is None:
        return None
    date_text = str(datestamp).strip()
    time_text = str(timestamp or '').strip() or '00:00:00'
    if not date_text:
        return None

    day = None
    for fmt in _DATE_FORMATS:
        try:
            day = datetime.strptime(date_text, fmt).date()
            break
        except ValueError:
            continue
    if day is None:
        return None

    for fmt in _TIME_FORMATS:
        try:
            clock = datetime.strptime(time_text, fmt).time()
            return datetime.combine(day, clock)
        except ValueError:
            continue
    # A readable date with an unreadable time is still worth more than nothing:
    # "last reported on the 28th" beats "never reported".
    return datetime.combine(day, datetime.min.time())


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


# dll_trips_auditor writes placeholder text where a NULL belongs — "NoData" in
# driver_id is the one that showed up first. Passing those through verbatim is
# how a customer gets told their driver was NoData, so they are read as absent.
_PLACEHOLDERS = frozenset((
    '', '-', '--', 'nodata', 'no data', 'none', 'null', 'nil',
    'n/a', 'na', 'unknown', 'undefined', 'not set', 'notset',
))


def _real(value):
    """The text, or None if it is a placeholder standing in for nothing."""
    text = str(value if value is not None else '').strip()
    return None if text.lower() in _PLACEHOLDERS else (text or None)


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
        'from': _real(loc0),
        'to': _real(loc1) if ended else None,
        'status': _real(state),
    }

    # Fuel only when something was actually measured. Both readings sitting at
    # zero means there is no fuel sensor, not that the trip burned nothing, and
    # "fuel_used: 0.0" is a claim about a measurement that never happened.
    fuel0, fuel1 = _num(f0), _num(f1)
    if (fuel0 is not None and fuel1 is not None
            and fuel0 >= fuel1 and (fuel0 or fuel1)):
        out['fuel_used'] = round(fuel0 - fuel1, 2)

    driver_id = _real(driver)
    if driver_id:
        out['driver_id'] = driver_id
    return out


def _points(imei, from_date, to_date, limit=_MAX_POINTS):
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

    wanted = re.sub(r'\s+', '', str(imei or ''))
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


def _segment(points):
    """Split a stream of fixes into trips on a gap in reporting."""
    trips, current = [], []
    previous = None
    for p in points:
        if previous and p['at'] and previous['at']:
            gap = (p['at'] - previous['at']).total_seconds() / 60.0
            if gap > _TRIP_GAP_MINUTES and current:
                trips.append(current)
                current = []
        current.append(p)
        previous = p
    if current:
        trips.append(current)
    return [t for t in trips if len(t) > 1]


def _summarise(trip):
    distance = 0.0
    for a, b in zip(trip, trip[1:]):
        distance += _metres(a['lat'], a['lon'], b['lat'], b['lon'])
    speeds = [p['speed'] for p in trip if p['speed'] is not None]
    moving = [s for s in speeds if s >= _MOVING_SPEED]
    start, end = trip[0], trip[-1]
    minutes = None
    if start['at'] and end['at']:
        minutes = round((end['at'] - start['at']).total_seconds() / 60.0, 1)
    return {
        'started_at': start['at'].isoformat(sep=' ') if start['at'] else None,
        'ended_at': end['at'].isoformat(sep=' ') if end['at'] else None,
        'duration_minutes': minutes,
        'distance_km': round(distance / 1000.0, 2),
        'max_speed_kph': round(max(speeds), 1) if speeds else None,
        'average_moving_speed_kph': (round(sum(moving) / len(moving), 1)
                                     if moving else None),
        'started_near': start['place'] or None,
        'ended_near': end['place'] or None,
        'fixes': len(trip),
    }


# ── Tools ───────────────────────────────────────────────────────────────────

def unit_find(query=None, client_uid=None, scope=None):
    """Which unit does the person mean? Matches plate, name, make/model or IMEI."""
    target = _target_client(scope, client_uid)
    if not target:
        return {'found': False,
                'reason': 'no client named — ask which client this is about'}
    units = _units_of(target)
    if not units:
        return {'found': False, 'reason': 'no units are registered to this account'}

    needle = re.sub(r'[^a-z0-9]', '', str(query or '').lower())
    if not needle:
        return {'found': True, 'match': 'all', 'count': len(units),
                'units': [{'imei': u['imei'], 'name': u['name'],
                           'vehicle': ' '.join(x for x in (u['make'], u['model']) if x)}
                          for u in units[:20]]}

    matches = []
    for u in units:
        hay = re.sub(r'[^a-z0-9]', '',
                     f"{u['name']}{u['vin']}{u['make']}{u['model']}{u['imei']}".lower())
        if needle in hay:
            matches.append(u)
    return {
        'found': bool(matches),
        'query': query,
        'count': len(matches),
        # More than one match is the answer, not a problem: the model should
        # ask which, rather than picking the first and being confidently wrong.
        'ambiguous': len(matches) > 1,
        'units': [{'imei': u['imei'], 'name': u['name'],
                   'vehicle': ' '.join(x for x in (u['make'], u['model']) if x),
                   'billing_status': u['billing_status']} for u in matches[:10]],
        'reason': None if matches else 'no unit on this account matches that',
    }


def unit_status(imei=None, client_uid=None, scope=None):
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


def unit_trips(imei=None, from_date=None, to_date=None, client_uid=None,
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


def _thin(points, spacing_m=_PROBE_SPACING_M, cap=_MAX_PROBES):
    """Keep points no closer together than [spacing_m], up to [cap]."""
    kept = []
    for p in points:
        if len(kept) >= cap:
            break
        if not kept or _metres(kept[-1]['lat'], kept[-1]['lon'],
                               p['lat'], p['lon']) >= spacing_m:
            kept.append(p)
    return kept


def _nearby(lat, lon, place_type, keyword=None):
    """One Places Nearby Search.

    Returns None when the server has no key (a configuration answer, not an
    empty result) and [] on any other failure — never raises into the turn.
    """
    from config import GOOGLE_MAPS_API_KEY
    if not GOOGLE_MAPS_API_KEY:
        return None
    params = {'location': f'{lat},{lon}', 'radius': _PROBE_RADIUS_M,
              'key': GOOGLE_MAPS_API_KEY}
    if place_type:
        params['type'] = place_type
    if keyword:
        params['keyword'] = keyword
    try:
        resp = requests.get(_PLACES_URL, params=params, timeout=_PLACES_TIMEOUT)
        body = resp.json()
    except Exception:
        return []
    if body.get('status') not in ('OK', 'ZERO_RESULTS'):
        return []
    return [{'name': r.get('name'), 'types': r.get('types', [])[:3]}
            for r in (body.get('results') or [])[:3]]


def unit_route_probe(imei=None, from_date=None, to_date=None, place_type=None,
                     keyword=None, min_speed=None, client_uid=None, scope=None):
    """Where along a unit's route was there a place of some kind — optionally
    only where it was travelling above min_speed km/h.

    This is the expensive tool. It filters by the condition first, thins what
    survives to one probe per _PROBE_SPACING_M metres, stops at _MAX_PROBES
    probes, and reports when the cap was reached so the answer can say how
    much of the route was actually checked.
    """
    unit = _owned(imei, scope, client_uid)
    if not unit:
        return {'found': False, 'reason': 'no such unit on this account'}
    if not from_date or not to_date:
        return {'found': False, 'reason': 'a date range is required, as DD-MM-YYYY'}
    if not place_type and not keyword:
        return {'found': False,
                'reason': 'name what to look for, e.g. place_type "mosque"'}

    points = _points(unit['imei'], from_date, to_date)
    if not points:
        return {'found': False, 'reason': 'this unit logged no positions in that range'}

    threshold = _num(min_speed)
    candidates = [p for p in points if threshold is None or p['speed'] >= threshold]
    if not candidates:
        return {'found': False, 'imei': unit['imei'], 'name': unit['name'],
                'reason': f'this unit never exceeded {threshold} km/h in that range',
                'fixes_read': len(points)}

    probes = _thin(candidates)
    hits = []
    for p in probes:
        found = _nearby(p['lat'], p['lon'], place_type, keyword)
        if found is None:
            return {'found': False,
                    'reason': 'place lookup is not configured on this server '
                              '(GOOGLE_MAPS_API_KEY is not set)'}
        if found:
            hits.append({
                'at': p['at'].isoformat(sep=' ') if p['at'] else None,
                'speed_kph': round(p['speed'], 1),
                'near': p['place'] or None,
                'lat': round(p['lat'], 5), 'lon': round(p['lon'], 5),
                'places': found,
            })

    return {
        'found': bool(hits),
        'imei': unit['imei'], 'name': unit['name'],
        'looked_for': place_type or keyword,
        'min_speed_kph': threshold,
        'fixes_read': len(points),
        'fixes_matching_speed': len(candidates),
        'places_checked': len(probes),
        # Said plainly so the answer can be honest about its own coverage.
        'coverage': ('every qualifying stretch was checked'
                     if len(probes) < _MAX_PROBES
                     else f'only the first {_MAX_PROBES} qualifying stretches '
                          f'were checked, spaced {_PROBE_SPACING_M}m apart'),
        'matches': hits,
        'reason': None if hits else 'nothing of that kind was found along the route',
    }


def fleet_activity(days=None, client_uid=None, scope=None):
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


# ── Tool specifications ─────────────────────────────────────────────────────

TOOL_SPECS = [
    {
        'type': 'function',
        'function': {
            'name': 'unit_find',
            'description': (
                'Find a vehicle on this account by number plate, unit name, '
                'make/model or IMEI. Use this FIRST whenever the person talks '
                'about a vehicle without giving an IMEI — including "my truck", '
                '"the lorry" or a plate like UBK 415K. Returns ambiguous: true '
                'when more than one unit matches, in which case ask which one '
                'rather than guessing. Call with no query to list the fleet.'),
            'parameters': {
                'type': 'object',
                'properties': {
                    'query': {'type': 'string',
                              'description': 'Plate, name, make/model or IMEI.'},
                    'client_uid': {'type': 'string',
                                   'description': ('Staff only: whose fleet to '
                                                   'search. Ignored for customers.')},
                },
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'unit_status',
            'description': (
                'What a unit is doing right now: when it last reported, how '
                'many hours ago, whether its billing is running and whether a '
                'pause rule is stopping it. Use this for "why is X offline", '
                '"is X working", "when did X last report". These are facts, '
                'not a diagnosis — read them and explain what they suggest.'),
            'parameters': {
                'type': 'object',
                'properties': {
                    'imei': {'type': 'string',
                             'description': 'The unit IMEI, from unit_find.'},
                    'client_uid': {'type': 'string', 'description': 'Staff only.'},
                },
                'required': ['imei'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'unit_trips',
            'description': (
                'Trip summaries for one unit over a date range: when each trip '
                'started and ended, distance, duration, top speed and roughly '
                'where. Use for "where did X go", "how far did X travel", "was '
                'X moving yesterday". Dates are DD-MM-YYYY.'),
            'parameters': {
                'type': 'object',
                'properties': {
                    'imei': {'type': 'string', 'description': 'From unit_find.'},
                    'from_date': {'type': 'string', 'description': 'DD-MM-YYYY.'},
                    'to_date': {'type': 'string', 'description': 'DD-MM-YYYY.'},
                    'client_uid': {'type': 'string', 'description': 'Staff only.'},
                },
                'required': ['imei', 'from_date', 'to_date'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'unit_route_probe',
            'description': (
                'Search along a unit\'s actual route for a kind of place — '
                '"did it pass a mosque", "was it near a school" — optionally '
                'only where it was travelling faster than a given speed. '
                'Expensive: it calls a mapping service per sampled point, so '
                'use it only when the question is genuinely about places along '
                'a route, and always pass min_speed when the question mentions '
                'speed. Read the coverage field and say how much was checked.'),
            'parameters': {
                'type': 'object',
                'properties': {
                    'imei': {'type': 'string', 'description': 'From unit_find.'},
                    'from_date': {'type': 'string', 'description': 'DD-MM-YYYY.'},
                    'to_date': {'type': 'string', 'description': 'DD-MM-YYYY.'},
                    'place_type': {
                        'type': 'string',
                        'description': ('A Google place type, e.g. mosque, '
                                        'church, school, hospital, gas_station.')},
                    'keyword': {'type': 'string',
                                'description': 'Free text, when no type fits.'},
                    'min_speed': {
                        'type': 'number',
                        'description': ('km/h. Only stretches at or above this '
                                        'are checked. Pass it whenever the '
                                        'question says fast, speeding or over '
                                        'a limit — it also cuts the cost.')},
                    'client_uid': {'type': 'string', 'description': 'Staff only.'},
                },
                'required': ['imei', 'from_date', 'to_date'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'fleet_activity',
            'description': (
                'How much each unit moved over the last N days — trips and '
                'distance per unit. Use for "how is my fleet doing", "which '
                'vehicle travelled most", "has anything not moved".'),
            'parameters': {
                'type': 'object',
                'properties': {
                    'days': {'type': 'integer', 'description': '1-31. Default 7.'},
                    'client_uid': {'type': 'string', 'description': 'Staff only.'},
                },
            },
        },
    },
]

_DISPATCH = {
    'unit_find': unit_find,
    'unit_status': unit_status,
    'unit_trips': unit_trips,
    'unit_route_probe': unit_route_probe,
    'fleet_activity': fleet_activity,
}


def dispatch(tool_name, arguments, scope=None):
    """Run a fleet tool.

    [scope] comes from the server, never the model. A `scope` key in the
    model's own arguments is dropped, and for a customer so is `client_uid` —
    otherwise naming someone else's client would be enough to read their fleet.
    """
    func = _DISPATCH.get(tool_name)
    if not func:
        return None
    arguments = dict(arguments or {})
    arguments.pop('scope', None)
    if not (scope or {}).get('is_staff'):
        arguments.pop('client_uid', None)
    try:
        return func(**arguments, scope=scope)
    except FleetUnavailable as error:
        # Said in the tool result, because that is what the model reads. The
        # instruction is part of the finding: a number here would be a guess.
        _warn('vehicle register unreachable (%s): %s', tool_name, error)
        return {
            'found': False,
            'unavailable': True,
            'reason': ('The vehicle register could not be reached just now. '
                       'This is a fault on our side and says NOTHING about '
                       'what this account owns. Tell the person you cannot '
                       'check their vehicles at the moment and that it should '
                       'be working again shortly. Do NOT say they have no '
                       'vehicles, do not give a count, and do not guess.'),
        }
    except TypeError as error:
        return {'error': f'bad arguments for {tool_name}: {error}'}
    except Exception as error:      # noqa: BLE001 - never break the turn
        return {'error': f'{tool_name} failed: {error}'}
