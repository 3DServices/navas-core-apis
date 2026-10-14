"""
fleet_summary -- the dashboard's fleet status and geofence presence, worked out
on the server.

The OLIWA app used to derive these figures itself: one latest-position request
per unit, six at a time, and nothing at all above 150 units. The reading now
happens once, on the server (endpoints/fleet.py), and this module holds the
arithmetic.

It is pure: no Flask, no database, no clock. Each unit arrives as a READING
already pulled from the stores:

    {'imei': ..., 'name': ...,
     'seen': datetime | None,     # when the unit last reported, local time
     'snapshot': dict | None,     # its latest live position (Redis), if any
     'unread': bool}              # the lookup FAILED -- not the same as silent

so tests/test_fleet_summary.py runs without a server.

The rules mirror the app's FleetKpis.derive (lib/models/fleet_kpis.dart), so
the dashboard shows the same numbers whichever side computes them.
"""

from datetime import timedelta

# A unit whose last report is older than this is silent (the app's
# FleetKpis.silentAfter).
SILENT_AFTER = timedelta(minutes=60)

# A position older than this is not used to place a unit inside a zone (the
# app looked back 30 days for each unit's latest fix).
ZONE_POSITION_MAX_AGE = timedelta(days=30)

MOVING_KMH = 5
MIN_SATELLITES = 4
TOP_ZONES = 3

STATES = ('moving', 'idling', 'parked', 'no_position', 'silent', 'unread')
SILENT_AGES = ('under_day', 'up_to_week', 'over_week', 'never')


def _num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def position(snapshot):
    """(lat, lng) of a snapshot, or None when it has no usable fix."""
    if not snapshot:
        return None
    lat = _num(snapshot.get('data_latitude'))
    lng = _num(snapshot.get('data_longitude'))
    if lat is None or lng is None or (lat == 0 and lng == 0):
        return None
    return lat, lng


def _ignition_on(value):
    return str(value or '').strip().lower() in ('1', 'on', 'true', 'yes')


def motion(snapshot):
    """moving / idling / parked, the console's normalizeStatus(): the feed's
    motion_state first, then speed, then ignition for a stationary unit."""
    state = str(snapshot.get('motion_state') or '').lower()
    if 'park' in state or 'stop' in state:
        return 'parked'
    if 'idl' in state:
        return 'idling'
    if 'mov' in state or 'driv' in state:
        return 'moving'
    speed = _num(snapshot.get('speed_log')) or 0.0
    if speed >= MOVING_KMH:
        return 'moving'
    if speed > 0:
        return 'idling'
    ignition = snapshot.get('ignition_status', snapshot.get('iginition'))
    return 'idling' if _ignition_on(ignition) else 'parked'


def classify(reading, now):
    """One of STATES.

    no_position is a unit that IS reporting but whose latest live position
    is missing, so whether it is moving cannot be said. unread is a unit whose
    lookup failed: nothing is known about it, and it is not called silent.
    """
    if reading.get('unread'):
        return 'unread'
    seen = reading.get('seen')
    if seen is None or now - seen > SILENT_AFTER:
        return 'silent'
    snapshot = reading.get('snapshot')
    if not snapshot:
        return 'no_position'
    return motion(snapshot)


def silent_age(seen, now):
    """Which SILENT_AGES bucket a silent unit falls in."""
    if seen is None:
        return 'never'
    age = now - seen
    if age > timedelta(days=7):
        return 'over_week'
    if age > timedelta(days=1):
        return 'up_to_week'
    return 'under_day'


def weak_gps(reading):
    """A reporting unit with no fix, or a fix from fewer than 4 satellites.
    A snapshot that does not say how many satellites is not counted as weak."""
    snapshot = reading.get('snapshot')
    if position(snapshot) is None:
        return True
    satellites = _num(snapshot.get('data_connected_satelites'))
    return satellites is not None and satellites < MIN_SATELLITES


def fleet_status(readings, now):
    counts = {s: 0 for s in STATES}
    ages = {a: 0 for a in SILENT_AGES}
    weak = 0
    for reading in readings:
        state = classify(reading, now)
        counts[state] += 1
        if state == 'silent':
            ages[silent_age(reading.get('seen'), now)] += 1
        elif state != 'unread' and weak_gps(reading):
            weak += 1
    return {
        'counts': counts,
        'silent_ages': ages,
        'weak_gps': weak,
        'reporting_now': sum(counts[s] for s in
                             ('moving', 'idling', 'parked', 'no_position')),
        'total': len(readings),
    }


CATEGORIES = ('general', 'depot', 'customer', 'restricted')

# Units named inside a restricted zone right now; the count is always whole.
RESTRICTED_NAMED = 5


def category_of(zone):
    value = str(zone.get('category') or '').strip().lower()
    return value if value in CATEGORIES else 'general'


def _is_exit(crossing):
    return str(crossing.get('type') or '').strip().lower() == 'exit'


def zone_visits(crossings):
    """Entry -> exit pairs per unit and zone: [{imei, zone, entered, left}].

    crossings  [{'imei', 'zone', 'type', 'at'}], any order. An exit with no
               entry before it (the entry was before the window) is not a
               visit; nor is an entry not yet left. A second entry without an
               exit between them restarts the visit, as the exit was missed.
    """
    open_at = {}
    visits = []
    for c in sorted(crossings, key=lambda c: c['at']):
        key = (c.get('imei'), str(c.get('zone') or '').strip().lower())
        if _is_exit(c):
            entered = open_at.pop(key, None)
            if entered is not None:
                visits.append({'imei': key[0], 'zone': c.get('zone'),
                               'entered': entered, 'left': c['at']})
        else:
            open_at[key] = c['at']
    return visits


def _median(values):
    ordered = sorted(values)
    if not ordered:
        return None
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def dwell(crossings, since, names=None):
    """Visits that ENDED at or after `since` (usually midnight): how many, the
    median and the longest, in whole minutes. names maps imei -> unit name."""
    names = names or {}
    done = [v for v in zone_visits(crossings) if v['left'] >= since]
    if not done:
        return {'visits': 0, 'median_minutes': None, 'longest': None}
    minutes = [(v['left'] - v['entered']).total_seconds() / 60 for v in done]
    longest = max(range(len(done)), key=lambda i: minutes[i])
    return {
        'visits': len(done),
        'median_minutes': int(round(_median(minutes))),
        'longest': {'unit': names.get(done[longest]['imei']) or done[longest]['imei'],
                    'zone': done[longest]['zone'],
                    'minutes': int(round(minutes[longest]))},
    }


def zone_presence(readings, zones, now, contains, crossings=(), since=None):
    """Units inside / outside the account's geofences right now.

    zones      [{'name', 'ring', 'shape', 'category'}]; corridors (shape
               'line') count toward zone_count but are not areas a unit is
               "inside", as in the app
    contains   contains(lat, lng, ring) -> bool (alert_engine.point_in_ring)
    crossings  recent geofence alerts, [{'imei', 'zone', 'type', 'at'}];
               'exit' is an exit, anything else an entry, as the app counts
               them. Those at or after `since` are today's.
    since      start of today; defaults to now's midnight
    """
    if since is None:
        since = now.replace(hour=0, minute=0, second=0, microsecond=0)
    areas = [z for z in zones if z.get('ring') and z.get('shape') != 'line']
    by_category = {c: {'zones': 0, 'units_inside': 0} for c in CATEGORIES}
    for zone in zones:
        by_category[category_of(zone)]['zones'] += 1
    zone_category = {str(z.get('name') or '').strip().lower(): category_of(z)
                     for z in zones}

    per_zone = {}
    restricted = []
    inside = outside = unplaced = 0
    for reading in readings:
        seen = reading.get('seen')
        fix = position(reading.get('snapshot'))
        if fix is None or seen is None or now - seen > ZONE_POSITION_MAX_AGE:
            unplaced += 1
            continue
        hit = set()
        for zone in areas:
            if contains(fix[0], fix[1], zone['ring']):
                hit.add(category_of(zone))
                per_zone[zone['name']] = per_zone.get(zone['name'], 0) + 1
                if category_of(zone) == 'restricted':
                    restricted.append({'unit': reading.get('name') or reading.get('imei'),
                                       'zone': zone['name']})
        for category in hit:
            by_category[category]['units_inside'] += 1
        if hit:
            inside += 1
        else:
            outside += 1

    busiest = sorted(per_zone.items(), key=lambda item: (-item[1], item[0]))
    today = [c for c in crossings if c.get('at') and c['at'] >= since]
    exits = sum(1 for c in today if _is_exit(c))
    restricted_entries = sum(
        1 for c in today if not _is_exit(c)
        and zone_category.get(str(c.get('zone') or '').strip().lower()) == 'restricted')
    names = {r.get('imei'): r.get('name') for r in readings}
    return {
        'zone_count': len(zones),
        'inside': inside,
        'outside': outside,
        'not_placed': unplaced,
        'top_zones': [{'name': name, 'units': units}
                      for name, units in busiest[:TOP_ZONES]],
        'entries_today': len(today) - exits,
        'exits_today': exits,
        'by_category': by_category,
        'restricted_inside': {'count': len(restricted),
                              'units': restricted[:RESTRICTED_NAMED]},
        'restricted_entries_today': restricted_entries,
        'dwell_today': dwell(crossings, since, names),
    }


def units_by_zone(readings, zones, now, contains):
    """Which unit is in which geofence right now, by name.

    zone_presence counts; this names, for Waswa ("which of my vehicles are
    inside Head Office?"). Same rules as the dashboard: a unit is placed only
    from a live fix no older than ZONE_POSITION_MAX_AGE. A corridor (shape
    'line') is a route, not an area -- a unit in its ring is "on route", kept
    apart from "inside" exactly as zone_presence leaves corridors out of it.

    zones  [{'name', 'ring', 'shape', 'category'}]
    Returns {'zones': {name: {'inside': [...], 'on_route': [...]}},
             'outside': [...], 'not_placed': [...]}.
    """
    per_zone = {z['name']: {'inside': [], 'on_route': []} for z in zones}
    outside, unplaced = [], []
    for reading in readings:
        label = reading.get('name') or reading.get('imei')
        seen = reading.get('seen')
        fix = position(reading.get('snapshot'))
        if fix is None or seen is None or now - seen > ZONE_POSITION_MAX_AGE:
            unplaced.append(label)
            continue
        placed = False
        for zone in zones:
            if not zone.get('ring') or not contains(fix[0], fix[1], zone['ring']):
                continue
            if zone.get('shape') == 'line':
                per_zone[zone['name']]['on_route'].append(label)
            else:
                per_zone[zone['name']]['inside'].append(label)
                placed = True
        if not placed:
            outside.append(label)
    return {'zones': per_zone, 'outside': outside, 'not_placed': unplaced}
