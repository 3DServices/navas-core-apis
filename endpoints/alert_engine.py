"""
alert_engine — event-rule alerts, decided on the server.

Event rules (dll_device_events) are created in the app and the console and
attached to units. This module checks them on a schedule:

    load the rules -> the units attached to each -> what is new for each unit
    since the last sweep (positions, ignition, heartbeat) -> what each rule
    makes of it (alert_conditions.py) -> write an alert only when the answer
    CHANGED, and remember the answer for next time.

Conditions checked: speed_threshold, ignition_change, device_offline and
geofence_breach. low_battery rules are counted but not checked — battery
readings from the trackers do not reach the server (alert_conditions.UNSUPPORTED).

Where the facts come from
-------------------------
Positions are read from Cassandra (location_store), from where this unit was
read up to last time (dll_alert_unit_cursor). Until migration 054 the engine
read the Postgres copy of dll_location_registry, whose newest row is from
August 2025, so every unit was "stale" and no geofence alert could fire.

Ignition is the unit's configured ignition input (dll_device_local_configs,
'ignition_detection') read from each fix's IO events. A unit without one is
not guessed from its speed, which would invent an "ignition on" every time a
parked vehicle's GPS drifted.

Offline is the unit's last heartbeat (dll_pulse_status_registry). A unit held
dark by a pause rule is not reported.

First sightings
---------------
The first time a rule meets a unit, its answer is recorded and nothing is sent
(except a unit already over a speed limit, which IS speeding). So attaching a
rule, or deploying this engine, does not announce every parked vehicle inside
a zone or every unit that died months ago.

Run it with POST /alerts/run (staff, or an internal caller sending
X-Service-Key), or let the app run it on a timer with ALERT_ENGINE_ENABLED=true.
"""

import json
import os
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import psycopg2
import psycopg2.extras
from flask import Blueprint, current_app, g, request

from . import alert_conditions as conditions
from . import location_store
from .globals import reply, require_staff, log_audit_event
from .notifier import parse_channels
from .owner_root import client_root

alerts_bp = Blueprint('alerts', __name__)

GEOFENCE_CONDITION = conditions.GEOFENCE

KAMPALA = ZoneInfo('Africa/Kampala')

# Positions are local (EAT) by date; record_timestamp is UTC. EAT is fixed +3.
_UTC_OFFSET = timedelta(hours=3)


def _max_position_age_days():
    try:
        return max(1, int(os.environ.get('ALERT_MAX_POSITION_AGE_DAYS', '2')))
    except ValueError:
        return 2


def _now_local():
    return datetime.now(KAMPALA).replace(tzinfo=None)


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
    """The rules the engine can check, and a count of those it cannot.

    Returns ({event_uid: rule}, skipped) where a rule is
    {event_uid, name, owner_uid, condition, config, channels} and skipped is
    {'unsupported': {condition: n}, 'invalid': n, 'unknown': n}.
    """
    cur.execute("SELECT * FROM dll_device_events")
    rules = {}
    skipped = {'unsupported': {}, 'invalid': 0, 'unknown': 0}
    for row in cur.fetchall():
        rule, why = parse_rule(row)
        if rule is not None:
            rules[rule['event_uid']] = rule
        elif why in ('invalid', 'unknown'):
            skipped[why] += 1
        else:
            skipped['unsupported'][why] = skipped['unsupported'].get(why, 0) + 1
    return rules, skipped


def parse_rule(row):
    """(rule, None) for a dll_device_events row the engine can check, else
    (None, why): 'invalid', 'unknown', or the unsupported condition."""
    condition = str(row.get('event_condition') or '').strip().lower()
    if condition in conditions.UNSUPPORTED:
        return None, condition
    if condition not in conditions.SUPPORTED:
        return None, 'unknown'
    config = conditions.parse_config(condition, row.get('event_condition_value'))
    if config is None:
        return None, 'invalid'
    return {
        'event_uid': str(row.get('event_local_uid')),
        'name': row.get('event_display_name') or 'Alert',
        'owner_uid': str(row.get('owner_org_uid') or ''),
        'condition': condition,
        'config': config,
        'channels': parse_channels(_alert_channels(row)),
    }, None


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


def load_units(session):
    """Units and the rules attached to each: [{imei, name, client, events}].

    Attachment lives in the unit registry (dll_device_basic_data.events_attached),
    which is what /devices/events/<event_uid>/attach writes.
    """
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


def load_paused(cur):
    """IMEIs a pause rule is holding dark on purpose (no offline alerts)."""
    try:
        cur.execute("SAVEPOINT paused")
        cur.execute("SELECT target_uid FROM dll_pause_rules WHERE active = TRUE")
        found = {str(r.get('target_uid')) for r in cur.fetchall()}
        cur.execute("RELEASE SAVEPOINT paused")
        return found
    except psycopg2.Error:
        cur.execute("ROLLBACK TO SAVEPOINT paused")
        return set()


def _tables_ready(cur):
    cur.execute("SELECT to_regclass('dll_alert_rule_state') IS NOT NULL AS a, "
                "to_regclass('dll_alert_unit_cursor') IS NOT NULL AS b")
    row = cur.fetchone() or {}
    return bool(row.get('a')) and bool(row.get('b'))


# ── What is new for one unit ─────────────────────────────────────────────────

def _day(d):
    return d.strftime('%d-%m-%Y')


def new_fixes(cur, session, imei, now_local):
    """(fixes oldest first, new cursor) — the positions since the last sweep.

    With no cursor, or one older than ALERT_MAX_POSITION_AGE_DAYS, the newest
    fix alone is taken: hours-old positions are not worth alerting on, and it
    gives every rule a starting answer.
    """
    cur.execute("SELECT last_fix_utc FROM dll_alert_unit_cursor WHERE device_imei = %s",
                (imei,))
    row = cur.fetchone()
    after = row.get('last_fix_utc') if row else None
    today = now_local.date()

    oldest = now_local - timedelta(days=_max_position_age_days())
    if after is None or after + _UTC_OFFSET < oldest:
        for day in (today, today - timedelta(days=1)):
            fix = location_store.latest_fix(session, imei, _day(day))
            if fix is not None:
                if fix['at'] is not None and fix['at'] < oldest:
                    return [], None
                return [fix], fix['at_utc']
        return [], None

    fixes, day = [], (after + _UTC_OFFSET).date()
    while day <= today:
        fixes.extend(location_store.fixes_after(session, imei, _day(day), after))
        day += timedelta(days=1)
    fixes.sort(key=lambda f: f['at_utc'] or f['at'] or datetime.min)
    newest = max((f['at_utc'] for f in fixes if f['at_utc'] is not None), default=None)
    return fixes, newest


def save_cursor(cur, imei, last_fix_utc):
    cur.execute(
        """
        INSERT INTO dll_alert_unit_cursor (device_imei, last_fix_utc, updated_at)
        VALUES (%s, %s, NOW())
        ON CONFLICT (device_imei) DO UPDATE
            SET last_fix_utc = GREATEST(dll_alert_unit_cursor.last_fix_utc,
                                        EXCLUDED.last_fix_utc),
                updated_at = NOW()
        """, (imei, last_fix_utc))


def ignition_source(session, imei):
    """The unit's configured ignition IO channel, or None."""
    rows = list(session.execute(
        "SELECT config_param_data_source_uid FROM dll_device_local_configs "
        "WHERE config_parameter=%s AND local_device_imei=%s ALLOW FILTERING;",
        ('ignition_detection', imei)))
    if len(rows) != 1:
        return None
    source = str(getattr(rows[0], 'config_param_data_source_uid', '') or '').strip()
    return source or None


def attach_ignition(session, fixes, source):
    """Set fix['ignition'] to 'ON', 'OFF' or None from each fix's IO events."""
    from .io_events_store import events_for
    events = events_for(session, [f.get('io_uid') for f in fixes if f.get('io_uid')])
    for fix in fixes:
        fix['ignition'] = None
        for event in events.get(str(fix.get('io_uid') or '').strip(), ()):
            if str(event.get('event_uid') or '').strip() != source:
                continue
            try:
                value = int(float(str(event.get('value')).strip()))
            except (TypeError, ValueError):
                break
            fix['ignition'] = {1: 'ON', 0: 'OFF'}.get(value)
            break


def last_heartbeat(session, statement, imei):
    """The unit's last heartbeat as a local datetime, or None."""
    row = session.execute(statement, (imei,)).one()
    if row is None:
        return None
    return location_store._stamp(getattr(row, 'last_heartbeat_date', None),
                                 getattr(row, 'last_heartbeat_time', None))


# ── Memory ───────────────────────────────────────────────────────────────────

def load_states(cur, imei):
    cur.execute("SELECT event_uid, condition, state FROM dll_alert_rule_state "
                "WHERE device_imei = %s", (imei,))
    return {str(r.get('event_uid')): r for r in cur.fetchall()}


def save_state(cur, rule, imei, state, alerted):
    cur.execute(
        """
        INSERT INTO dll_alert_rule_state
            (event_uid, device_imei, condition, state, last_alert_at, updated_at)
        VALUES (%s, %s, %s, %s::jsonb, CASE WHEN %s THEN NOW() END, NOW())
        ON CONFLICT (event_uid, device_imei) DO UPDATE
            SET condition = EXCLUDED.condition,
                state = EXCLUDED.state,
                last_alert_at = COALESCE(EXCLUDED.last_alert_at,
                                         dll_alert_rule_state.last_alert_at),
                updated_at = NOW()
        """,
        (rule['event_uid'], imei, rule['condition'], json.dumps(state), bool(alerted)),
    )


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


def write_alert(cur, rule, unit, alert):
    """One row in the alerts list the console and the app read — filed under
    the client (account_root), which is what they ask for, not under the
    user who created the rule."""
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
            unit['imei'], unit['name'], rule['condition'],
            alert['trigger_value'], alert.get('geozone_name') or '',
            alert.get('breach_type') or '',
            json.dumps(rule['channels']),
            client_root(cur, rule['owner_uid'] or unit['client']),
        ),
    )


# ── The sweep ────────────────────────────────────────────────────────────────

def _count(summary, key, condition, n=1):
    summary[key][condition] = summary[key].get(condition, 0) + n


def sweep_unit(cur, session, unit, unit_rules, zones, now_local, live, summary,
               heartbeat_stmt, paused):
    """Check every rule attached to one unit. Writes only when live."""
    imei = unit['imei']
    wanted = {r['condition'] for r in unit_rules}

    fixes, cursor = [], None
    if wanted & {conditions.SPEED, conditions.IGNITION, conditions.GEOFENCE}:
        fixes, cursor = new_fixes(cur, session, imei, now_local)
        if not fixes:
            summary['units_no_new_positions'] += 1

    if conditions.IGNITION in wanted and fixes:
        source = ignition_source(session, imei)
        if source is None:
            summary['units_without_ignition_input'] += 1
            for fix in fixes:
                fix['ignition'] = None
        else:
            attach_ignition(session, fixes, source)

    states = load_states(cur, imei)
    seen = None
    if conditions.OFFLINE in wanted:
        seen = last_heartbeat(session, heartbeat_stmt, imei)

    def remembered(rule):
        row = states.get(rule['event_uid'])
        if row is None or row.get('condition') != rule['condition']:
            return None
        state = row.get('state')
        if isinstance(state, str):
            try:
                state = json.loads(state)
            except (TypeError, ValueError):
                return None
        return state if isinstance(state, dict) else None

    def deliver(rule, alerts):
        for alert in alerts:
            _count(summary, 'alerts_by_condition', rule['condition'])
            summary['alerts'] += 1
            if live:
                write_alert(cur, rule, unit, alert)

    for rule in unit_rules:
        condition = rule['condition']
        if condition == conditions.GEOFENCE:
            continue
        prior = remembered(rule)
        if condition == conditions.SPEED:
            if not fixes:
                continue
            alerts, state = conditions.evaluate_speed(rule['config'], prior, fixes)
        elif condition == conditions.IGNITION:
            if not fixes:
                continue
            alerts, state = conditions.evaluate_ignition(rule['config'], prior, fixes)
        elif condition == conditions.OFFLINE:
            alerts, state = conditions.evaluate_offline(
                rule['config'], prior, seen, now_local, paused=imei in paused)
        else:
            continue
        deliver(rule, alerts)
        if live and state != prior:
            save_state(cur, rule, imei, state, bool(alerts))

    geofence_rules = [r for r in unit_rules if r['condition'] == conditions.GEOFENCE]
    if geofence_rules and fixes:
        watched = {z for r in geofence_rules for z in r['config']['zones'] if z in zones}
        known = load_presence(cur, imei)
        presence = {z: bool(known[z].get('is_inside')) for z in watched if z in known}
        summary['first_seen'] += len(watched - set(presence))

        def contains(zone_uid, lat, lon):
            zone = zones.get(zone_uid)
            return None if zone is None else point_in_ring(lat, lon, zone['ring'])

        crossings, inside = conditions.geofence_crossings(watched, presence, fixes, contains)
        names = {z: zones[z]['name'] for z in watched}
        for rule in geofence_rules:
            deliver(rule, conditions.geofence_alerts(rule['config'], crossings, names))
        if live:
            ref = fixes[-1].get('at_utc') or fixes[-1].get('data_idx') or ''
            for zone_uid, now_inside in inside.items():
                save_presence(cur, imei, zone_uid, now_inside, ref)

    if live and cursor is not None:
        save_cursor(cur, imei, cursor)


def run_alert_sweep(live=True):
    """Check every unit attached to a rule once.

    live=False does everything except writing alerts and state, so a sweep can
    be inspected before it is allowed to notify anyone.
    Returns a summary dict — safe to log.
    """
    summary = {
        'rules': 0, 'rules_by_condition': {}, 'rules_not_checked': {},
        'units_checked': 0, 'units_no_new_positions': 0,
        'units_without_ignition_input': 0, 'first_seen': 0,
        'alerts': 0, 'alerts_by_condition': {}, 'live': bool(live), 'errors': [],
    }
    from .devices import get_cassandra_session

    connection = psycopg2.connect(current_app.config['db_link'])
    try:
        with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            if not _tables_ready(cur):
                summary['errors'].append(
                    'migration 054 has not been applied (dll_alert_rule_state)')
                return summary

            rules, skipped = load_rules(cur)
            summary['rules'] = len(rules)
            for rule in rules.values():
                _count(summary, 'rules_by_condition', rule['condition'])
            summary['rules_not_checked'] = {
                **{c: f'{n} rule(s): {conditions.UNSUPPORTED[c]}'
                   for c, n in skipped['unsupported'].items()},
                **({'invalid_value': skipped['invalid']} if skipped['invalid'] else {}),
                **({'unknown_condition': skipped['unknown']} if skipped['unknown'] else {}),
            }
            if not rules:
                return summary

            zone_uids = {z for r in rules.values()
                         if r['condition'] == conditions.GEOFENCE
                         for z in r['config']['zones']}
            zones = load_zones(cur, zone_uids)
            paused = load_paused(cur)
            connection.commit()

            session = get_cassandra_session()
            if session is None:
                summary['errors'].append('unit registry unavailable')
                return summary
            try:
                units = load_units(session)
                heartbeat_stmt = session.prepare(
                    "SELECT last_heartbeat_date, last_heartbeat_time "
                    "FROM dll_pulse_status_registry WHERE device_data_imei = ? LIMIT 1")
            except Exception as error:      # noqa: BLE001
                summary['errors'].append(f'unit registry: {error}')
                return summary

            now_local = _now_local()
            for unit in units:
                unit_rules = [rules[e] for e in unit['events'] if e in rules
                              and rules[e]['condition'] not in conditions.ON_FUEL_ISSUE]
                if not unit_rules:
                    continue
                summary['units_checked'] += 1
                # One unit's failure must not lose the others' work, so each
                # unit is its own transaction.
                try:
                    sweep_unit(cur, session, unit, unit_rules, zones, now_local,
                               live, summary, heartbeat_stmt, paused)
                    connection.commit()
                except Exception as error:      # noqa: BLE001
                    connection.rollback()
                    if len(summary['errors']) < 20:
                        summary['errors'].append(f"{unit['imei']}: {error}")
    finally:
        connection.close()
    return summary


# ── Fuel issues ──────────────────────────────────────────────────────────────

def unit_with_rules(session, imei):
    """{imei, name, client, events} for one unit, or None."""
    stmt = session.prepare(
        "SELECT device_imei, device_name, device_client, events_attached "
        "FROM dll_device_basic_data WHERE device_imei = ?")
    row = session.execute(stmt, (str(imei),)).one()
    if row is None:
        return None
    attached = row.events_attached
    if isinstance(attached, str):
        try:
            attached = json.loads(attached)
        except (TypeError, ValueError):
            attached = []
    return {'imei': str(row.device_imei), 'name': row.device_name or str(row.device_imei),
            'client': str(row.device_client or ''),
            'events': [str(e) for e in (attached or [])]}


def fuel_issue_alerts(cur, issue, profile):
    """Alerts for one FuelMath issue just recorded, from the fuel rules
    attached to its vehicle. Returns how many were written.

    cur      the recording's cursor (RealDictCursor); the alerts commit with
             the issue
    issue    fuel_rules.public_issue() of the new issue
    profile  the vehicle's fuel profile row, or None
    """
    from .devices import get_cassandra_session
    session = get_cassandra_session()
    if session is None:
        return 0
    unit = unit_with_rules(session, issue.get('device_imei'))
    if unit is None or not unit['events']:
        return 0
    cur.execute("SELECT * FROM dll_device_events WHERE event_local_uid = ANY(%s) "
                "AND LOWER(event_condition) = ANY(%s)",
                (unit['events'], list(conditions.ON_FUEL_ISSUE)))
    written = 0
    for row in cur.fetchall():
        rule, _ = parse_rule(row)
        if rule is None:
            continue
        if rule['condition'] == conditions.FUEL_FLAGGED:
            alerts = conditions.evaluate_fuel_flagged(rule['config'], issue)
        else:
            alerts = conditions.evaluate_fuel_consumption(rule['config'], issue, profile)
        for alert in alerts:
            write_alert(cur, rule, unit, alert)
            written += 1
    return written


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

    if summary.get('alerts') and live:
        by = ', '.join(f'{n} {c}' for c, n in summary['alerts_by_condition'].items())
        log_audit_event(
            actor='alert-engine', action='ALERTS_SENT',
            obj=f"{summary['alerts']} alert(s) ({by}) from {summary['units_checked']} unit(s)",
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
                rules, skipped = load_rules(cur)
                by_condition = {}
                for rule in rules.values():
                    by_condition[rule['condition']] = by_condition.get(rule['condition'], 0) + 1
                cur.execute("SELECT COUNT(*) AS units, MAX(last_checked) AS last_checked "
                            "FROM dll_geozone_presence")
                presence = cur.fetchone() or {}
                last_sweep, units = presence.get('last_checked'), None
                if _tables_ready(cur):
                    cur.execute("SELECT COUNT(*) AS units, MAX(updated_at) AS last "
                                "FROM dll_alert_unit_cursor")
                    row = cur.fetchone() or {}
                    units = row.get('units', 0)
                    last_sweep = row.get('last') or last_sweep
                cur.execute("SELECT condition, COUNT(*) AS n FROM dll_event_notifications "
                            "WHERE condition = ANY(%s) "
                            "AND date_triggered > NOW() - INTERVAL '24 hours' "
                            "GROUP BY condition", (list(conditions.SUPPORTED),))
                recent = {r['condition']: r['n'] for r in cur.fetchall()}
    finally:
        connection.close()
    return reply('success', 200, 'Alert engine status', {
        'rules_by_condition': by_condition,
        'rules_not_checked': {**skipped['unsupported'],
                              'invalid_value': skipped['invalid'],
                              'unknown_condition': skipped['unknown']},
        'geofence_rules': by_condition.get(conditions.GEOFENCE, 0),
        'tracked_unit_zones': presence.get('units', 0),
        'tracked_units': units,
        'migration_054_applied': units is not None,
        'last_sweep': str(last_sweep or ''),
        'alerts_last_24h': recent,
    })
