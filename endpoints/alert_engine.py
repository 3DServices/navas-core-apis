"""
alert_engine — geofence alerts, decided on the server.

Until now the OLIWA console worked out geofence entries and exits in the
browser and posted them to /notifications/log. That had three problems:

  * the first position a browser saw inside a zone was reported as an ENTRY,
    so opening the tracking screen invented alerts for vehicles that had been
    parked inside a zone all along;
  * a rule fired for every unit on the account, whether or not the unit was
    attached to it;
  * nothing was detected at all unless somebody had the screen open, and two
    open screens produced two alerts.

This module does the same work on the server, on a schedule:

    load the geofence rules -> the units attached to each rule -> each unit's
    latest position -> inside or outside each zone -> compare with what was
    recorded last time (dll_geozone_presence) -> write an alert only when the
    answer CHANGED.

The first time a unit is seen against a zone its position is recorded and no
alert is sent, so a vehicle already parked inside a zone is not reported as
having just entered it. A unit whose position hasn't moved on since the last
sweep is skipped, and a position older than ALERT_MAX_POSITION_AGE_DAYS is
treated as "we don't know where it is" rather than as a crossing.

Run it with POST /alerts/run (staff, or an internal caller sending
X-Service-Key), or let the app run it on a timer with ALERT_ENGINE_ENABLED=true.
"""

import json
import os
import uuid
from datetime import datetime, timedelta

import psycopg2
import psycopg2.extras
from flask import Blueprint, current_app, g, request

from .globals import reply, require_staff, log_audit_event
from .notifier import parse_channels

alerts_bp = Blueprint('alerts', __name__)

GEOFENCE_CONDITION = 'geofence_breach'


def _max_position_age_days():
    try:
        return max(1, int(os.environ.get('ALERT_MAX_POSITION_AGE_DAYS', '2')))
    except ValueError:
        return 2


# ── Geometry ─────────────────────────────────────────────────────────────────

def point_in_ring(lat, lng, ring):
    """Ray casting. `ring` is a list of [lng, lat] pairs, as stored in
    dll_geozones.geozone_points (the console uses the same test)."""
    inside = False
    count = len(ring)
    if count < 3:
        return False
    j = count - 1
    for i in range(count):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if ((yi > lat) != (yj > lat)) and \
                (lng < (xj - xi) * (lat - yi) / ((yj - yi) or 1e-12) + xi):
            inside = not inside
        j = i
    return inside


def _ring(raw):
    """dll_geozones.geozone_points -> [[lng, lat], ...] (empty when unusable)."""
    if not raw:
        return []
    points = raw
    if isinstance(points, str):
        try:
            points = json.loads(points)
        except (TypeError, ValueError):
            return []
    ring = []
    for point in points if isinstance(points, list) else []:
        try:
            if isinstance(point, dict):
                lng = float(point.get('lng', point.get('longitude')))
                lat = float(point.get('lat', point.get('latitude')))
            else:
                lng, lat = float(point[0]), float(point[1])
        except (TypeError, ValueError, KeyError, IndexError):
            continue
        ring.append([lng, lat])
    return ring


# ── Loading ──────────────────────────────────────────────────────────────────

def load_rules(cur):
    """Active geofence rules: {event_uid: {...}} with their zones and
    which crossing they care about."""
    cur.execute("SELECT * FROM dll_device_events")
    rules = {}
    for row in cur.fetchall():
        if str(row.get('event_condition') or '').strip().lower() != GEOFENCE_CONDITION:
            continue
        try:
            value = json.loads(row.get('event_condition_value') or '{}')
        except (TypeError, ValueError):
            continue
        zones = [str(z) for z in (value.get('zones') or []) if z]
        if not zones:
            continue
        breach = str(value.get('breach_type') or 'both').lower()
        rules[str(row.get('event_local_uid'))] = {
            'event_uid': str(row.get('event_local_uid')),
            'name': row.get('event_display_name') or 'Geofence alert',
            'owner_uid': str(row.get('owner_org_uid') or ''),
            'zones': zones,
            'breach_type': breach if breach in ('enter', 'exit', 'both') else 'both',
            'channels': parse_channels(_alert_channels(row)),
        }
    return rules


def _alert_channels(row):
    raw = row.get('notification_alert_method') or row.get('alert_channels') or ''
    if isinstance(raw, str) and raw.strip().startswith('['):
        try:
            return json.loads(raw)
        except (TypeError, ValueError):
            return raw
    return raw


def load_zones(cur, zone_uids):
    """{geozone_uid: {'name':.., 'ring':[[lng,lat],..]}} for the zones in use."""
    if not zone_uids:
        return {}
    cur.execute(
        "SELECT geozone_uid, geozone_name, geozone_points FROM dll_geozones "
        "WHERE geozone_uid = ANY(%s)", (list(zone_uids),)
    )
    zones = {}
    for row in cur.fetchall():
        ring = _ring(row.get('geozone_points'))
        if ring:
            zones[str(row.get('geozone_uid'))] = {
                'name': row.get('geozone_name') or 'Zone',
                'ring': ring,
            }
    return zones


def load_units():
    """Units and the rules attached to each: [{imei, name, client, events}].

    Attachment lives in the unit registry (dll_device_basic_data.events_attached),
    which is what /devices/events/<event_uid>/attach writes.
    """
    from .devices import get_cassandra_session
    session = get_cassandra_session()
    if session is None:
        raise RuntimeError('unit registry unavailable')
    rows = session.execute(
        "SELECT device_imei, device_name, device_client, events_attached "
        "FROM dll_device_basic_data"
    )
    units = []
    for row in rows:
        attached = row.events_attached
        if isinstance(attached, str):
            try:
                attached = json.loads(attached)
            except (TypeError, ValueError):
                attached = []
        units.append({
            'imei': str(row.device_imei),
            'name': row.device_name or str(row.device_imei),
            'client': str(row.device_client or ''),
            'events': [str(e) for e in (attached or [])],
        })
    return units


def latest_position(cur, imei):
    """(lat, lng, data_idx, date) of the unit's newest fix, or None."""
    cur.execute(
        "SELECT data_idx, data_latitude, data_longitude, local_system_datestamp "
        "FROM dll_location_registry WHERE data_device_imei = %s "
        "ORDER BY data_idx DESC LIMIT 1", (str(imei),)
    )
    row = cur.fetchone()
    if not row:
        return None
    try:
        lat = float(row.get('data_latitude'))
        lng = float(row.get('data_longitude'))
    except (TypeError, ValueError):
        return None
    return {
        'lat': lat,
        'lng': lng,
        'idx': str(row.get('data_idx') or ''),
        'date': _as_date(row.get('local_system_datestamp')),
    }


def _as_date(value):
    if isinstance(value, datetime):
        return value.date()
    for fmt in ('%d-%m-%Y', '%Y-%m-%d'):
        try:
            return datetime.strptime(str(value), fmt).date()
        except (TypeError, ValueError):
            continue
    return None


def load_presence(cur, imei):
    cur.execute(
        "SELECT geozone_uid, is_inside, last_position_ref FROM dll_geozone_presence "
        "WHERE device_imei = %s", (str(imei),)
    )
    return {str(r.get('geozone_uid')): r for r in cur.fetchall()}


def save_presence(cur, imei, zone_uid, inside, position_ref):
    cur.execute(
        """
        INSERT INTO dll_geozone_presence
            (device_imei, geozone_uid, is_inside, last_position_ref, last_checked)
        VALUES (%s, %s, %s, %s, NOW())
        ON CONFLICT (device_imei, geozone_uid) DO UPDATE
            SET is_inside = EXCLUDED.is_inside,
                last_position_ref = EXCLUDED.last_position_ref,
                last_checked = NOW()
        """,
        (str(imei), str(zone_uid), bool(inside), str(position_ref)),
    )


def write_alert(cur, rule, unit, zone_name, crossing):
    """One row in the alerts list the console and the app read."""
    cur.execute(
        """
        INSERT INTO dll_event_notifications
            (notification_uid, event_uid, event_name, device_imei, device_name,
             condition, trigger_value, geozone_name, breach_type, alert_channels,
             owner_uid, is_read, date_triggered)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, FALSE, NOW())
        """,
        (
            str(uuid.uuid4()), rule['event_uid'], rule['name'],
            unit['imei'], unit['name'], GEOFENCE_CONDITION,
            f"{crossing}:{zone_name}", zone_name, crossing,
            json.dumps(rule['channels']),
            rule['owner_uid'] or unit['client'],
        ),
    )


# ── The sweep ────────────────────────────────────────────────────────────────

def run_alert_sweep(live=True):
    """Check every unit attached to a geofence rule once.

    live=False does everything except writing alerts and presence, so a sweep
    can be inspected before it is allowed to notify anyone.
    Returns a summary dict — safe to log.
    """
    summary = {
        'rules': 0, 'units_checked': 0, 'units_skipped_no_position': 0,
        'units_skipped_stale': 0, 'units_skipped_unchanged': 0,
        'first_seen': 0, 'alerts': 0, 'live': bool(live), 'errors': [],
    }
    connection = psycopg2.connect(current_app.config['db_link'])
    try:
        with connection:
            with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                rules = load_rules(cur)
                summary['rules'] = len(rules)
                if not rules:
                    return summary

                zone_uids = {z for rule in rules.values() for z in rule['zones']}
                zones = load_zones(cur, zone_uids)

                try:
                    units = load_units()
                except Exception as error:
                    summary['errors'].append(f'unit registry: {error}')
                    return summary

                oldest_allowed = datetime.utcnow().date() - timedelta(days=_max_position_age_days())

                for unit in units:
                    unit_rules = [rules[e] for e in unit['events'] if e in rules]
                    if not unit_rules:
                        continue
                    summary['units_checked'] += 1

                    position = latest_position(cur, unit['imei'])
                    if position is None:
                        summary['units_skipped_no_position'] += 1
                        continue
                    if position['date'] is not None and position['date'] < oldest_allowed:
                        summary['units_skipped_stale'] += 1
                        continue

                    presence = load_presence(cur, unit['imei'])
                    wanted = {z for rule in unit_rules for z in rule['zones']}
                    # Nothing new to say: same position, and every zone this
                    # unit is watched against has already been answered.
                    unchanged = position['idx'] and wanted <= set(presence) and all(
                        presence[z].get('last_position_ref') == position['idx']
                        for z in wanted
                    )
                    if unchanged:
                        summary['units_skipped_unchanged'] += 1
                        continue

                    for zone_uid in wanted:
                        zone = zones.get(zone_uid)
                        if zone is None:
                            continue
                        inside = point_in_ring(position['lat'], position['lng'], zone['ring'])
                        known = presence.get(zone_uid)

                        if known is None:
                            # First time we've looked: remember where it is,
                            # don't call it a crossing.
                            summary['first_seen'] += 1
                            if live:
                                save_presence(cur, unit['imei'], zone_uid, inside, position['idx'])
                            continue

                        was_inside = bool(known.get('is_inside'))
                        if was_inside == inside:
                            if live:
                                save_presence(cur, unit['imei'], zone_uid, inside, position['idx'])
                            continue

                        crossing = 'enter' if inside else 'exit'
                        for rule in unit_rules:
                            if zone_uid not in rule['zones']:
                                continue
                            if rule['breach_type'] != 'both' and rule['breach_type'] != crossing:
                                continue
                            summary['alerts'] += 1
                            if live:
                                write_alert(cur, rule, unit, zone['name'], crossing)
                        if live:
                            save_presence(cur, unit['imei'], zone_uid, inside, position['idx'])
    finally:
        connection.close()
    return summary


# ── Routes ───────────────────────────────────────────────────────────────────

@alerts_bp.route("/alerts/run", methods=["POST"])
def run_alerts():
    """Run one sweep now. Internal callers send X-Service-Key; staff may also
    run it by hand. Body: {"data": {"live": true}} — live=false is a dry run."""
    if not getattr(g, 'service_call', False):
        user = getattr(g, 'current_user', None)
        if not user:
            return reply('error', 401, 'Please sign in to continue.', '')

    payload = request.get_json(silent=True) or {}
    data = payload.get('data') or {}
    live = data.get('live', True)
    live = str(live).lower() not in ('false', '0', 'no')

    try:
        summary = run_alert_sweep(live=live)
    except Exception as error:
        return reply('error', 500, f'Alert sweep failed: {error}', '')

    if summary.get('alerts'):
        log_audit_event(
            actor='alert-engine', action='ALERTS_SENT',
            obj=f"{summary['alerts']} geofence alert(s) from {summary['units_checked']} unit(s)",
            domain='ALARM', severity='Info',
        )
    return reply('success', 200, 'Alert sweep complete', summary)


@alerts_bp.route("/alerts/health", methods=["GET"])
@require_staff('alarms.view', 'devices.view')
def alerts_health():
    """What the engine knows right now — for the ops screen."""
    connection = psycopg2.connect(current_app.config['db_link'])
    try:
        with connection:
            with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                rules = load_rules(cur)
                cur.execute("SELECT COUNT(*) AS units, MAX(last_checked) AS last_checked "
                            "FROM dll_geozone_presence")
                row = cur.fetchone() or {}
                cur.execute("SELECT COUNT(*) AS recent FROM dll_event_notifications "
                            "WHERE condition = %s AND date_triggered > NOW() - INTERVAL '24 hours'",
                            (GEOFENCE_CONDITION,))
                recent = (cur.fetchone() or {}).get('recent', 0)
    finally:
        connection.close()
    return reply('success', 200, 'Alert engine status', {
        'geofence_rules': len(rules),
        'tracked_unit_zones': row.get('units', 0),
        'last_sweep': str(row.get('last_checked') or ''),
        'alerts_last_24h': recent,
    })
