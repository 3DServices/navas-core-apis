"""
alert_conditions — what each event-rule condition means, with no I/O.

alert_engine.py reads the rules, the units and their new positions, and hands
them here; this module decides which alerts that adds up to and what to
remember for next time. Keeping it free of databases is what lets every rule
below be tested with plain dicts.

Each evaluator takes the rule, the state remembered from the previous sweep
(None the first time a rule meets a unit) and what is new since then, and
returns (alerts, state). An alert is a dict:

    {'trigger_value': str, 'at': datetime | None,
     'geozone_name': str, 'breach_type': str}

The rule that runs through all of them: an alert is sent when the answer
CHANGES, never because it is still true. A vehicle doing 95 in an 80 zone is
reported once when it goes over, not on every sweep it stays over.
"""

import json
from datetime import datetime

SPEED = 'speed_threshold'
IGNITION = 'ignition_change'
OFFLINE = 'device_offline'
GEOFENCE = 'geofence_breach'
BATTERY = 'low_battery'
FUEL_FLAGGED = 'fuel_issue_flagged'
FUEL_CONSUMPTION = 'high_fuel_consumption'

SUPPORTED = (SPEED, IGNITION, OFFLINE, GEOFENCE, FUEL_FLAGGED, FUEL_CONSUMPTION)

# Checked when FuelMath records an issue (fuel_registry.record_issue), not on
# the sweep: the facts they need exist only at that moment.
ON_FUEL_ISSUE = (FUEL_FLAGGED, FUEL_CONSUMPTION)

# Conditions a rule can be saved with but the server cannot check, and why.
# The sweep counts these rather than pretending to watch them.
UNSUPPORTED = {
    BATTERY: 'battery readings from the trackers do not reach the server',
}

# A speeding episode ends when the speed falls this far below the limit, so a
# vehicle hovering around 80 in an 80 zone is not reported on every fix.
SPEED_HYSTERESIS_KMH = 5.0

# Faster than this is a bad GPS fix, not a vehicle.
SPEED_PLAUSIBLE_KMH = 250.0

SPEED_LIMIT_MIN, SPEED_LIMIT_MAX = 5.0, 250.0

# Shorter than this and a tracker between two reports looks offline.
OFFLINE_MIN_MINUTES = 5
OFFLINE_MAX_MINUTES = 60 * 24 * 30

# However much arrives at once, one rule says at most this much about one unit
# in one sweep — an ignition wire that flickers must not send forty SMS.
MAX_ALERTS_PER_SWEEP = 3

# High consumption is judged over at least this distance between full tanks;
# over less, a few litres either way swing the km/L too far to mean anything.
CONSUMPTION_MIN_KM = 100.0
CONSUMPTION_PCT_MIN, CONSUMPTION_PCT_MAX = 5, 100


# ── Rule parsing ─────────────────────────────────────────────────────────────

def _number(value):
    try:
        return float(str(value).replace(',', '').strip())
    except (TypeError, ValueError):
        return None


def _value_text(raw):
    """event_condition_value as plain text. Some clients send JSON such as
    {"value": "80"}; most send the bare value."""
    text = str(raw if raw is not None else '').strip()
    if text.startswith('{'):
        try:
            data = json.loads(text)
        except (TypeError, ValueError):
            return text
        if isinstance(data, dict):
            for key in ('value', 'limit', 'minutes', 'direction', 'state'):
                if data.get(key) not in (None, ''):
                    return str(data[key]).strip()
    return text


def parse_config(condition, raw_value):
    """The settings a rule's condition needs, or None when the rule cannot be
    checked as saved (an unreadable value, an unknown condition).

    speed_threshold  {'limit': km/h}
    ignition_change  {'direction': 'on' | 'off' | 'both'}
    device_offline   {'minutes': int}
    geofence_breach  {'zones': [uid, ...], 'breach_type': 'enter'|'exit'|'both'}
    """
    condition = str(condition or '').strip().lower()

    if condition == SPEED:
        limit = _number(_value_text(raw_value))
        if limit is None or not SPEED_LIMIT_MIN <= limit <= SPEED_LIMIT_MAX:
            return None
        return {'limit': limit}

    if condition == IGNITION:
        text = _value_text(raw_value).lower()
        if text in ('on', '1', 'true', 'ignition on', 'start', 'started'):
            return {'direction': 'on'}
        if text in ('off', '0', 'false', 'ignition off', 'stop', 'stopped'):
            return {'direction': 'off'}
        return {'direction': 'both'}

    if condition == OFFLINE:
        minutes = _number(_value_text(raw_value))
        if minutes is None:
            return None
        minutes = int(round(minutes))
        if not OFFLINE_MIN_MINUTES <= minutes <= OFFLINE_MAX_MINUTES:
            return None
        return {'minutes': minutes}

    if condition == FUEL_FLAGGED:
        # "all", or the flag codes to alert on: a JSON list, {"flags": [...]}
        # or comma-separated. Which codes exist is fuel_rules' business;
        # devices._event_value_error checks them when the rule is saved.
        text = str(raw_value if raw_value is not None else '').strip()
        codes = None
        if text.startswith('[') or text.startswith('{'):
            try:
                data = json.loads(text)
            except (TypeError, ValueError):
                return None
            codes = data.get('flags') if isinstance(data, dict) else data
            if codes in (None, 'all'):
                return {'flags': None}
            if not isinstance(codes, list):
                return None
        elif text.lower() in ('', 'all', 'any'):
            return {'flags': None}
        else:
            codes = text.split(',')
        codes = sorted({str(c).strip().lower() for c in codes if str(c).strip()})
        if not codes or not all(c.replace('_', '').isalpha() for c in codes):
            return None
        return {'flags': codes}

    if condition == FUEL_CONSUMPTION:
        # Percent more fuel than expected before alerting; "profile" (or
        # nothing) uses each vehicle's own tolerance from its fuel profile.
        text = _value_text(raw_value).lower().rstrip('%').strip()
        if text in ('', 'profile', 'default'):
            return {'pct': None}
        pct = _number(text)
        if pct is None or not CONSUMPTION_PCT_MIN <= pct <= CONSUMPTION_PCT_MAX:
            return None
        return {'pct': pct}

    if condition == GEOFENCE:
        try:
            value = json.loads(raw_value or '{}')
        except (TypeError, ValueError):
            return None
        if not isinstance(value, dict):
            return None
        zones = [str(z) for z in (value.get('zones') or []) if z]
        if not zones:
            return None
        breach = str(value.get('breach_type') or 'both').lower()
        return {'zones': zones,
                'breach_type': breach if breach in ('enter', 'exit', 'both') else 'both'}

    return None


def _alert(trigger_value, at=None, geozone_name='', breach_type=''):
    return {'trigger_value': trigger_value, 'at': at,
            'geozone_name': geozone_name, 'breach_type': breach_type}


def _clock(at):
    return at.strftime('%H:%M') if at is not None else ''


# ── Speed ────────────────────────────────────────────────────────────────────

def evaluate_speed(config, state, fixes):
    """One alert each time the unit goes over the limit.

    fixes are oldest first; each has 'speed' and 'at'. The episode ends when
    the speed drops SPEED_HYSTERESIS_KMH below the limit. A unit already over
    the limit the first time it is seen IS speeding, so that is reported.
    """
    limit = config['limit']
    over = bool((state or {}).get('over'))
    alerts = []
    for fix in fixes:
        speed = _number(fix.get('speed'))
        if speed is None or speed < 0 or speed > SPEED_PLAUSIBLE_KMH:
            continue
        if not over and speed > limit:
            over = True
            if len(alerts) < MAX_ALERTS_PER_SWEEP:
                alerts.append(_alert(
                    f'Speeding at {speed:.0f} km/h (limit {limit:g} km/h)', fix.get('at')))
        elif over and speed <= limit - SPEED_HYSTERESIS_KMH:
            over = False
    return alerts, {'over': over}


# ── Ignition ─────────────────────────────────────────────────────────────────

def evaluate_ignition(config, state, fixes):
    """One alert per ignition change in the rule's direction.

    fixes are oldest first; each has 'ignition' as 'ON', 'OFF' or None (not
    known for that fix, which is skipped rather than read as a change). The
    first known reading is remembered without an alert: it says what the
    ignition is, not that it just changed.
    """
    direction = config['direction']
    last = (state or {}).get('ignition')
    alerts = []
    for fix in fixes:
        now = fix.get('ignition')
        if now not in ('ON', 'OFF'):
            continue
        if last is not None and now != last:
            wanted = (direction == 'both'
                      or (direction == 'on' and now == 'ON')
                      or (direction == 'off' and now == 'OFF'))
            if wanted and len(alerts) < MAX_ALERTS_PER_SWEEP:
                alerts.append(_alert(
                    f'Ignition {"on" if now == "ON" else "off"} '
                    f'at {_clock(fix.get("at"))}'.strip(), fix.get('at')))
        last = now
    return alerts, {'ignition': last}


# ── Offline ──────────────────────────────────────────────────────────────────

def _duration(minutes):
    minutes = int(minutes)
    if minutes < 60:
        return f'{minutes} min'
    hours, rest = divmod(minutes, 60)
    if hours < 48:
        return f'{hours} h {rest} min' if rest else f'{hours} h'
    return f'{hours // 24} days'


def evaluate_offline(config, state, last_seen, now, paused=False):
    """One alert when the unit has been silent for the rule's minutes, and
    nothing more until it reports again.

    last_seen  the unit's last heartbeat (local time), None if it never
               reported — which sends nothing: a unit that was never fitted
               has not gone offline.
    paused     a pause rule is holding the unit dark on purpose, so silence is
               expected; the state is still tracked so that un-pausing a unit
               that is still silent does not report it as newly offline.

    The first time a rule meets a unit its current answer is recorded without
    an alert, so attaching a rule to a unit that has been dead for months does
    not announce it as news.
    """
    if last_seen is None:
        return [], dict(state or {})
    silent = (now - last_seen).total_seconds() / 60.0
    offline = silent >= config['minutes']
    if state is None or 'offline' not in state:
        return [], {'offline': offline}
    alerts = []
    if offline and not state.get('offline') and not paused:
        alerts.append(_alert(
            f'No report for {_duration(silent)} '
            f'(last at {last_seen.strftime("%d %b %H:%M")})', now))
    return alerts, {'offline': offline}


# ── Geofence ─────────────────────────────────────────────────────────────────

def geofence_crossings(zone_uids, presence, fixes, contains):
    """The crossings a run of fixes makes, zone by zone.

    zone_uids  the zones any of the unit's rules watch
    presence   {zone_uid: bool} — inside or not at the last sweep; a zone
               missing from it has never been answered, and its first answer
               is recorded without a crossing
    fixes      oldest first, each with 'lat', 'lon' and 'at'
    contains   contains(zone_uid, lat, lon) -> bool, None for an unknown zone

    Returns ([(zone_uid, 'enter' | 'exit', fix), ...], new_presence). Every
    fix is tested, not just the newest, so a vehicle that passes through a
    small zone between two sweeps is still reported.
    """
    inside = dict(presence)
    crossings = []
    for fix in fixes:
        for zone_uid in zone_uids:
            now = contains(zone_uid, fix['lat'], fix['lon'])
            if now is None:
                continue
            if zone_uid not in inside:
                inside[zone_uid] = now
                continue
            if inside[zone_uid] != now:
                crossings.append((zone_uid, 'enter' if now else 'exit', fix))
                inside[zone_uid] = now
    return crossings, inside


def geofence_alerts(config, crossings, zone_names):
    """The crossings one geofence rule cares about, as alerts."""
    alerts = []
    for zone_uid, crossing, fix in crossings:
        if zone_uid not in config['zones']:
            continue
        if config['breach_type'] not in ('both', crossing):
            continue
        name = zone_names.get(zone_uid, zone_uid)
        alerts.append(_alert(f'{crossing}:{name}', fix.get('at'), name, crossing))
        if len(alerts) >= MAX_ALERTS_PER_SWEEP:
            break
    return alerts


# ── Fuel (FuelMath issues) ───────────────────────────────────────────────────

def _litres(value):
    return f'{float(value):.1f}'.rstrip('0').rstrip('.') + ' L'


def _issued_at(issue):
    """issued_at as a datetime: public_issue() sends ISO text."""
    at = issue.get('issued_at')
    if isinstance(at, str):
        try:
            return datetime.fromisoformat(at.strip().replace(' ', 'T'))
        except ValueError:
            return None
    return at if hasattr(at, 'strftime') else None


def _issue_line(issue):
    at = _issued_at(issue)
    when = at.strftime('%d %b %H:%M') if at else ''
    where = str(issue.get('station_name') or '').strip()
    parts = [_litres(issue.get('litres') or 0)]
    if where:
        parts.append(f'at {where}')
    if when:
        parts.append(f'on {when}')
    return ' '.join(parts)


def evaluate_fuel_flagged(config, issue):
    """One alert when a recorded issue has a discrepancy the rule watches.

    issue is fuel_rules.public_issue(): 'flags' is [{code, kind, message}],
    and only kind 'discrepancy' counts — a notice ("no fuel profile") is not
    something to send an SMS about.
    """
    wanted = config.get('flags')
    found = [f for f in issue.get('flags') or ()
             if f.get('kind') == 'discrepancy'
             and (wanted is None or f.get('code') in wanted)]
    if not found or issue.get('voided'):
        return []
    reasons = ' '.join(str(f.get('message') or f.get('code')).strip() for f in found)
    return [_alert(f'Fuel issue flagged: {_issue_line(issue)}. {reasons}',
                   _issued_at(issue))]


def evaluate_fuel_consumption(config, issue, profile):
    """One alert when a full tank closes a span that used more fuel than the
    vehicle's expected km/L allows.

    Measured as FuelMath measures it: litres since the previous full tank
    against tracker km over the same span. Needs a full tank, a profile with
    a baseline, and at least CONSUMPTION_MIN_KM driven.
    """
    if not issue.get('full_tank') or issue.get('voided') or not profile:
        return []
    km = _number(issue.get('km_since_full'))
    used = _number(issue.get('litres_since_full'))
    baseline = _number(profile.get('baseline_km_per_l'))
    if not km or not used or not baseline or km < CONSUMPTION_MIN_KM:
        return []
    pct = config.get('pct')
    if pct is None:
        pct = _number(profile.get('tolerance_pct'))
        if pct is None:
            return []
    expected = km / baseline
    excess = (used / expected - 1) * 100
    if excess <= pct:
        return []
    return [_alert(
        f'High fuel consumption: {km / used:.1f} km/L over {km:.0f} km, '
        f'expected {baseline:g} km/L ({excess:.0f}% more fuel than expected, '
        f'{used - expected:.0f} L)', _issued_at(issue))]
