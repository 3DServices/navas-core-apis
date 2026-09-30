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

def _pg():
    return psycopg2.connect(current_app.config['db_link'])


def _cassandra():
    from .devices import get_cassandra_session
    return get_cassandra_session()


def _units_of(client_uid):
    """Every unit registered to a client. [] when Cassandra is unreachable."""
    session = _cassandra()
    if session is None or not client_uid:
        return []
    try:
        stmt = session.prepare(
            "SELECT device_imei, device_name, device_car_make, device_car_model, "
            "device_vin_number, device_billing_status "
            "FROM dll_device_basic_data WHERE device_client = ? ALLOW FILTERING")
        rows = session.execute(stmt, (str(client_uid),))
    except Exception:
        return []
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


def _stamp(datestamp, timestamp):
    """dll_location_registry stores DD-MM-YYYY and HH:MM:SS as text."""
    try:
        return datetime.strptime(f'{datestamp} {timestamp}', '%d-%m-%Y %H:%M:%S')
    except (TypeError, ValueError):
        return None


def _points(imei, from_date, to_date, limit=_MAX_POINTS):
    """Position fixes, oldest first. Unreadable rows are skipped, not guessed."""
    sql = ("SELECT data_latitude, data_longitude, speed_log, "
           "       local_system_datestamp, local_system_timestamp, geocoded_location "
           "FROM dll_location_registry "
           "WHERE data_device_imei = %s "
           "  AND TO_DATE(local_system_datestamp, 'DD-MM-YYYY') "
           "      BETWEEN TO_DATE(%s, 'DD-MM-YYYY') AND TO_DATE(%s, 'DD-MM-YYYY') "
           "ORDER BY data_idx ASC LIMIT %s")
    conn = _pg()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, (str(imei), str(from_date), str(to_date), int(limit)))
            rows = cur.fetchall() if cur.rowcount > 0 else []
    finally:
        conn.close()

    out = []
    for lat, lon, speed, datestamp, timestamp, place in rows:
        la, lo = _num(lat), _num(lon)
        if la is None or lo is None or (la == 0 and lo == 0):
            continue
        out.append({
            'lat': la, 'lon': lo,
            'speed': _num(speed) or 0.0,
            'at': _stamp(datestamp, timestamp),
            'place': str(place or '').strip(),
        })
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
    """Why a unit is or is not reporting — facts only, no diagnosis."""
    unit = _owned(imei, scope, client_uid)
    if not unit:
        return {'found': False, 'reason': 'no such unit on this account'}

    status = {'found': True, 'imei': unit['imei'], 'name': unit['name'],
              'vehicle': ' '.join(x for x in (unit['make'], unit['model']) if x),
              'billing_status': unit['billing_status'] or 'unrecorded'}

    session = _cassandra()
    if session is None:
        status['heartbeat'] = 'the unit registry could not be reached'
    else:
        try:
            stmt = session.prepare(
                "SELECT last_heartbeat_date, last_heartbeat_time "
                "FROM dll_pulse_status_registry WHERE device_data_imei = ? LIMIT 1")
            row = session.execute(stmt, (unit['imei'],)).one()
        except Exception:
            row = None
        if row is None:
            status['last_reported_at'] = None
            status['heartbeat'] = 'this unit has never reported'
        else:
            seen = _stamp(getattr(row, 'last_heartbeat_date', None),
                          getattr(row, 'last_heartbeat_time', None))
            status['last_reported_at'] = seen.isoformat(sep=' ') if seen else None
            if seen:
                hours = (datetime.now() - seen).total_seconds() / 3600.0
                status['hours_since_last_report'] = round(hours, 1)
                status['reporting_today'] = seen.date() == datetime.now().date()

    conn = _pg()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT mode, active FROM dll_pause_rules "
                        "WHERE target = %s AND active = TRUE", (unit['imei'],))
            rules = cur.fetchall() if cur.rowcount > 0 else []
            status['paused_by_rule'] = [r[0] for r in rules] or None
    except psycopg2.Error:
        status['paused_by_rule'] = 'pause rules could not be read'
    finally:
        conn.close()

    return status


def unit_trips(imei=None, from_date=None, to_date=None, client_uid=None, scope=None):
    """Trip summaries for a unit. Summaries — never the raw fixes."""
    unit = _owned(imei, scope, client_uid)
    if not unit:
        return {'found': False, 'reason': 'no such unit on this account'}
    if not from_date or not to_date:
        return {'found': False,
                'reason': 'a date range is required, as DD-MM-YYYY'}

    points = _points(unit['imei'], from_date, to_date)
    if not points:
        return {'found': False, 'imei': unit['imei'], 'name': unit['name'],
                'reason': 'this unit logged no positions in that range'}

    trips = [_summarise(t) for t in _segment(points)]
    return {
        'found': True,
        'imei': unit['imei'],
        'name': unit['name'],
        'from': from_date, 'to': to_date,
        'trip_count': len(trips),
        'total_distance_km': round(sum(t['distance_km'] for t in trips), 2),
        'fixes_read': len(points),
        'truncated': len(points) >= _MAX_POINTS,
        'trips': trips[:40],
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


def fleet_activity(days=7, client_uid=None, scope=None):
    """How much the fleet moved over the last N days."""
    target = _target_client(scope, client_uid)
    if not target:
        return {'found': False, 'reason': 'no client named'}
    units = _units_of(target)
    if not units:
        return {'found': False, 'reason': 'no units are registered to this account'}

    try:
        window = max(1, min(31, int(days)))
    except (TypeError, ValueError):
        window = 7
    to_date = datetime.now()
    from_date = to_date - timedelta(days=window)
    fmt = '%d-%m-%Y'

    rows = []
    for unit in units[:25]:
        points = _points(unit['imei'], from_date.strftime(fmt), to_date.strftime(fmt))
        trips = [_summarise(t) for t in _segment(points)] if points else []
        rows.append({
            'imei': unit['imei'], 'name': unit['name'],
            'trips': len(trips),
            'distance_km': round(sum(t['distance_km'] for t in trips), 1),
            'last_fix': (points[-1]['at'].isoformat(sep=' ')
                         if points and points[-1]['at'] else None),
        })

    active = [r for r in rows if r['trips'] > 0]
    return {
        'found': True,
        'days': window,
        'units_considered': len(rows),
        'units_that_moved': len(active),
        'total_distance_km': round(sum(r['distance_km'] for r in rows), 1),
        'units': sorted(rows, key=lambda r: -r['distance_km'])[:25],
        'note': ('only the first 25 units were measured'
                 if len(units) > 25 else None),
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
    except TypeError as error:
        return {'error': f'bad arguments for {tool_name}: {error}'}
    except Exception as error:      # noqa: BLE001 - never break the turn
        return {'error': f'{tool_name} failed: {error}'}
