"""
driver_scoring -- driver scorecards: every driver starts at 100 for a period
and each violation deducts the points the client's scoring rule says.

Routes in drivers.py; the Driver Scorecard report in driver_report.py.

Violations and where they come from
-----------------------------------
  overspeeding          a speed_threshold alert (dll_event_notifications)
  geofence_breach       a geofence_breach alert
  fuel_exception        a FuelMath fuel issue a check flagged (dll_fuel_issues),
                        made to the driver
  unauthorised_driving  a driver_unauthorised alert saying the driver kept a
                        vehicle after their permit expired (a refused
                        assignment is not the driver's fault and is not
                        counted)

Alerts only exist where the client has set up the matching event rule and
attached it to vehicles, so a client with no speed rule has no overspeeding to
deduct. dll_triggered_events, which the overspeeding and night-driving reports
read, holds no rows in production (see geofence_report.py), so it is not used.

An alert counts against the driver it records (migration 060), or failing
that the driver assigned to the vehicle when it fired.

Not measured yet: harsh braking, acceleration and cornering, and night
driving. The trackers' events for them do not reach the server (the IO audit),
so rules can be saved for them but deduct nothing until they do.

Pure -- no Flask, no database, no clock -- so tests/test_driver_scoring.py runs
without a server.
"""

START = 100

# code -> (label, default points, measured)
VIOLATIONS = {
    'overspeeding': ('Overspeeding', 5, True),
    'geofence_breach': ('Geofence breach', 3, True),
    'fuel_exception': ('Fuel exception', 5, True),
    'unauthorised_driving': ('Driving with an expired permit', 20, True),
    'harsh_braking': ('Harsh braking', 3, False),
    'harsh_acceleration': ('Harsh acceleration', 3, False),
    'harsh_cornering': ('Harsh cornering', 3, False),
    'night_driving': ('Night driving', 2, False),
}

MEASURED = tuple(c for c, (_, _, m) in VIOLATIONS.items() if m)

# 0 switches a violation off for the client.
POINTS_MIN, POINTS_MAX = 0, 100

# (lowest score, grade, label), best first.
GRADES = (
    (90, 'A', 'Excellent'),
    (75, 'B', 'Good'),
    (60, 'C', 'Fair'),
    (0, 'D', 'Poor'),
)

# Old free-text violation_parameter values, read as codes.
_ALIASES = {
    'overspeed': 'overspeeding', 'speeding': 'overspeeding', 'speed': 'overspeeding',
    'geofence': 'geofence_breach', 'geozone': 'geofence_breach',
    'fuel': 'fuel_exception', 'fuel_issue': 'fuel_exception',
    'unauthorised': 'unauthorised_driving', 'unauthorized_driving': 'unauthorised_driving',
    'harsh_brake': 'harsh_braking', 'braking': 'harsh_braking',
    'harsh_accel': 'harsh_acceleration', 'acceleration': 'harsh_acceleration',
    'cornering': 'harsh_cornering', 'night': 'night_driving',
}


def violation_code(value):
    """A violation_parameter as a code in VIOLATIONS, or None. Accepts the
    old free text ('harsh braking', 'Overspeeding')."""
    code = '_'.join(str(value or '').strip().lower().replace('-', ' ').split())
    code = _ALIASES.get(code, code)
    return code if code in VIOLATIONS else None


def _int(value):
    try:
        n = float(str(value).replace(',', '').strip())
    except (TypeError, ValueError):
        return None
    return int(n) if n == int(n) else None


# ── rules ────────────────────────────────────────────────────────────────────

def default_rules():
    """The built-in rule for every violation. A client's own rule for a
    violation replaces the default for it (effective_rules); deleting it goes
    back to the default."""
    return [{'score_uid': f'default:{code}', 'score_name': label,
             'violation_parameter': code, 'points_denomination': points,
             'max_deduction': None, 'is_default': True}
            for code, (label, points, _) in VIOLATIONS.items()]


def validate_rule(data):
    """(clean, errors) for a scoring rule a client sends.

    clean   {score_name, violation_parameter, points_denomination,
             max_deduction}
    errors  {field: message}, empty when the rule is fine"""
    errors, clean = {}, {}
    code = violation_code(data.get('violation_parameter'))
    if code is None:
        errors['violation_parameter'] = ('Choose what the rule scores: '
                                         + ', '.join(VIOLATIONS) + '.')
    clean['violation_parameter'] = code

    points = _int(data.get('points_denomination'))
    if points is None or not POINTS_MIN <= points <= POINTS_MAX:
        errors['points_denomination'] = (f'Points must be a whole number from '
                                         f'{POINTS_MIN} to {POINTS_MAX}.')
    clean['points_denomination'] = points

    cap_raw = data.get('max_deduction')
    cap = None
    if cap_raw not in (None, ''):
        cap = _int(cap_raw)
        if cap is None or not 1 <= cap <= START:
            errors['max_deduction'] = (f'The most a rule takes off must be a whole '
                                       f'number from 1 to {START}, or empty.')
        elif points and cap < points:
            errors['max_deduction'] = 'The most a rule takes off cannot be less than one violation.'
    clean['max_deduction'] = cap

    name = str(data.get('score_name') or '').strip()[:100]
    clean['score_name'] = name or (VIOLATIONS[code][0] if code else '')
    return clean, errors


def public_rule(row):
    """A stored rule as the apps receive it."""
    code = violation_code(row.get('violation_parameter'))
    label, _, measured = VIOLATIONS.get(code, (str(row.get('violation_parameter') or ''), 0, False))
    return {
        'score_uid': row.get('score_uid'),
        'score_name': row.get('score_name') or label,
        'violation_parameter': code or row.get('violation_parameter'),
        'violation_label': label,
        'points_denomination': _int(row.get('points_denomination')),
        'max_deduction': _int(row.get('max_deduction')),
        'measured': measured,
        'is_default': bool(row.get('is_default')),
        # Kept for clients that read the old columns: a score starts at 100
        # and every rule takes points off.
        'score_order': 'highest_best',
        'score_points_order': 'deduct',
    }


def effective_rules(own):
    """The rules a client is scored by: its own rule for each violation it has
    one for, the default for the rest, in VIOLATIONS order.
    own: stored rows (dicts) of the client."""
    mine = {}
    for row in own:
        code = violation_code(row.get('violation_parameter'))
        if code is not None:
            mine[code] = row
    defaults = {r['violation_parameter']: r for r in default_rules()}
    return [public_rule(mine.get(code) or defaults[code]) for code in VIOLATIONS]


def rules_by_code(rules):
    """{code: rule} from public_rule dicts, later rules winning."""
    out = {}
    for rule in rules:
        code = violation_code(rule.get('violation_parameter'))
        if code is not None and rule.get('points_denomination'):
            out[code] = rule
    return out


# ── scoring ──────────────────────────────────────────────────────────────────

def grade(score):
    """(letter, label) for a score, or (None, 'No driving') when None."""
    if score is None:
        return None, 'No driving'
    for floor, letter, label in GRADES:
        if score >= floor:
            return letter, label
    return GRADES[-1][1], GRADES[-1][2]


def scorecard(driver, violations, rules, drove):
    """One driver's scorecard for a period.

    driver      {'driver_uid', 'full_name', ...}
    violations  [{'code', 'at', 'vehicle', 'detail'}, ...] for this driver
    rules       {code: public_rule} (rules_by_code)
    drove       whether they held a vehicle at any time in the period

    A driver who neither drove nor has a violation is not scored: 100 would
    say they drove well, when they did not drive."""
    counts, deducted = {}, {}
    for v in violations:
        counts[v['code']] = counts.get(v['code'], 0) + 1
    for code, n in counts.items():
        rule = rules.get(code)
        if not rule or not VIOLATIONS.get(code, ('', 0, False))[2]:
            continue
        points = n * int(rule['points_denomination'])
        cap = rule.get('max_deduction')
        deducted[code] = min(points, int(cap)) if cap else points
    total = sum(deducted.values())
    scored = drove or bool(violations)
    score = max(0, START - total) if scored else None
    letter, label = grade(score)
    breakdown = [
        {'violation': code, 'label': VIOLATIONS[code][0], 'count': counts.get(code, 0),
         'points_each': int(rules[code]['points_denomination']) if code in rules else 0,
         'deducted': deducted.get(code, 0)}
        for code in VIOLATIONS if counts.get(code) or code in deducted
    ]
    return {
        'driver_uid': driver.get('driver_uid'),
        'full_name': driver.get('full_name'),
        'status': driver.get('status'),
        'score': score,
        'grade': letter,
        'grade_label': label,
        'deducted': total,
        'violation_count': sum(counts.values()),
        'breakdown': breakdown,
        'violations': sorted(violations, key=lambda v: str(v.get('at') or ''), reverse=True),
    }


def rank(cards):
    """The scorecards best first, each with 'rank' (ties share a rank).
    Unscored drivers come last, unranked."""
    scored = sorted((c for c in cards if c['score'] is not None),
                    key=lambda c: (-c['score'], c['violation_count'],
                                   str(c.get('full_name') or '').lower()))
    previous, place = None, 0
    for i, card in enumerate(scored, start=1):
        key = (card['score'], card['violation_count'])
        if key != previous:
            place, previous = i, key
        card['rank'] = place
    rest = sorted((c for c in cards if c['score'] is None),
                  key=lambda c: str(c.get('full_name') or '').lower())
    for card in rest:
        card['rank'] = None
    return scored + rest


# ── attributing violations ───────────────────────────────────────────────────

def driver_at(assignments, imei, at):
    """The driver_uid assigned to [imei] at [at] (a datetime), or None.
    assignments: [{'driver_uid', 'device_imei', 'assigned_at', 'ended_at'}]."""
    if not imei or at is None:
        return None
    for a in assignments:
        if a.get('device_imei') != imei:
            continue
        start, end = a.get('assigned_at'), a.get('ended_at')
        if start is not None and start <= at and (end is None or at < end):
            return a.get('driver_uid')
    return None


def alert_violation(alert):
    """The violation code an alert row is, or None when it is not one.
    alert: {'condition', 'trigger_value', ...}"""
    condition = str(alert.get('condition') or '').strip().lower()
    if condition == 'speed_threshold':
        return 'overspeeding'
    if condition == 'geofence_breach':
        return 'geofence_breach'
    if condition == 'driver_unauthorised':
        # Only the driver keeping a vehicle on an expired permit; a refused
        # assignment attempt was somebody else's doing.
        text = str(alert.get('trigger_value') or '').lower()
        return None if 'was refused' in text else 'unauthorised_driving'
    return None


def fuel_violation(issue):
    """'fuel_exception' for a fuel issue a check flagged, else None.
    issue: fuel_rules.public_issue() shape."""
    if issue.get('voided'):
        return None
    flagged = [f for f in issue.get('flags') or () if f.get('kind') == 'discrepancy']
    return 'fuel_exception' if flagged else None
