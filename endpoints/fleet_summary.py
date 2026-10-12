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


def zone_presence(readings, zones, now, contains, crossings=()):
    """Units inside / outside the account's geofences right now.

    zones      [{'name', 'ring', 'shape'}]; corridors (shape 'line') count
               toward zone_count but are not areas a unit is "inside", as in
               the app
    contains   contains(lat, lng, ring) -> bool (alert_engine.point_in_ring)
    crossings  today's geofence alerts' breach_type values; 'exit' is an
               exit, anything else an entry, as the app counts them
    """
    areas = [z for z in zones if z.get('ring') and z.get('shape') != 'line']
    per_zone = {}
    inside = outside = unplaced = 0
    for reading in readings:
        seen = reading.get('seen')
        fix = position(reading.get('snapshot'))
        if fix is None or seen is None or now - seen > ZONE_POSITION_MAX_AGE:
            unplaced += 1
            continue
        hit = False
        for zone in areas:
            if contains(fix[0], fix[1], zone['ring']):
                hit = True
                per_zone[zone['name']] = per_zone.get(zone['name'], 0) + 1
        if hit:
            inside += 1
        else:
            outside += 1

    busiest = sorted(per_zone.items(), key=lambda item: (-item[1], item[0]))
    exits = sum(1 for c in crossings if str(c or '').strip().lower() == 'exit')
    return {
        'zone_count': len(zones),
        'inside': inside,
        'outside': outside,
        'not_placed': unplaced,
        'top_zones': [{'name': name, 'units': units}
                      for name, units in busiest[:TOP_ZONES]],
        'entries_today': len(crossings) - exits,
        'exits_today': exits,
    }
