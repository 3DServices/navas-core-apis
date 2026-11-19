"""
driver_report -- the rows of the driver reports
(POST /data-stream/reports/drivers/<kind>/generate-data, driver_registry.py).

  registry     every registered driver and their details, one section
  assignments  which vehicles each driver held, from when to when and why it
               ended, one section per driver
  compliance   permit expiry, missing details and status, one section per
               verdict (Non-compliant, Needs attention, Compliant, Inactive)
  fuel         fuel issued to each driver: litres, cost, payment and anything
               FuelMath flagged, one section per driver
  scorecard    each driver's score for the period (100 less their
               violations, driver_scoring.py), ranked, one section

Every report route returns [{section: [row, ...]}, ...]; the app's report
table, PDF and Excel read it. Values are text as the app shows them. Money is
whole shillings with thousands separators.

Pure -- no Flask, no database, no clock (`today`/`now` are passed in), and no
imports from sibling modules (loading the endpoints package starts the whole
app), so tests/test_driver_report.py runs without a server. The fuel labels
come in from fuel_report as arguments.
"""

from datetime import date, datetime

KINDS = ('registry', 'assignments', 'compliance', 'fuel', 'scorecard')

# Reports that cover a period and so need start_date/end_date. Registry and
# compliance describe drivers as they are today.
DATED = ('assignments', 'fuel', 'scorecard')

EMPTY_MESSAGES = {
    'registry': 'No Drivers Found: register drivers under Drivers first',
    'assignments': 'No Driver Assignments Found for the selected drivers and dates',
    'compliance': 'No Drivers Found: register drivers under Drivers first',
    'fuel': 'No Fuel Issued to the selected drivers in these dates',
    'scorecard': 'No Drivers Found: register drivers under Drivers first',
}

STATUS_LABELS = {
    'active': 'Active', 'suspended': 'Suspended',
    'blacklisted': 'Blacklisted', 'inactive': 'Inactive',
}

PERMIT_LABELS = {'valid': 'Valid', 'expiring': 'Expiring', 'expired': 'Expired'}

# dll_driver_assignments.end_reason, as driver_registry writes it.
END_REASON_LABELS = {
    'reassigned': 'Moved to another vehicle',
    'replaced': 'Another driver assigned',
    'unassigned': 'Unassigned',
    'suspended': 'Driver suspended',
    'blacklisted': 'Driver blacklisted',
    'inactive': 'Driver deactivated',
}

# Compliance verdicts, worst first: the order the sections come in.
NON_COMPLIANT = 'Non-compliant'
NEEDS_ATTENTION = 'Needs attention'
COMPLIANT = 'Compliant'
INACTIVE = 'Inactive'
VERDICTS = (NON_COMPLIANT, NEEDS_ATTENTION, COMPLIANT, INACTIVE)

# Optional details a compliance check asks for (permit number, expiry and
# classes are required at registration, so they are never missing).
OPTIONAL_DETAILS = (
    ('national_id', 'National ID'),
    ('ibutton_id', 'iButton tag'),
    ('emergency_phone', 'Emergency contact'),
    ('photo_file', 'Photo'),
)

ALL_DRIVERS = 'All drivers'


# ── formatting ───────────────────────────────────────────────────────────────

def _num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def money(value):
    n = _num(value)
    return '' if n is None else f'{round(n):,}'


def litres(value):
    n = _num(value)
    return '' if n is None else f'{n:.2f}'.rstrip('0').rstrip('.')


def _as_datetime(value):
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    if isinstance(value, str) and value.strip():
        try:
            return datetime.fromisoformat(value.strip().replace(' ', 'T'))
        except ValueError:
            return None
    return None


def _as_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    at = _as_datetime(value)
    return at.date() if at else None


def day(value):
    d = _as_date(value)
    return d.isoformat() if d else ''


def clock(value):
    at = _as_datetime(value)
    return at.strftime('%H:%M') if at and isinstance(value, (datetime, str)) else ''


def duration(start, end):
    """'3 d 4 h', '5 h 12 min' or '40 min' between two datetimes."""
    a, b = _as_datetime(start), _as_datetime(end)
    if a is None or b is None or b < a:
        return ''
    minutes = int((b - a).total_seconds() // 60)
    days, rest = divmod(minutes, 24 * 60)
    hours, mins = divmod(rest, 60)
    if days:
        return f'{days} d {hours} h'
    if hours:
        return f'{hours} h {mins} min'
    return f'{mins} min'


def _text(value):
    return '' if value is None else str(value).strip()


def _classes(value):
    if isinstance(value, (list, tuple)):
        codes = value
    else:
        codes = [c for c in _text(value).split(',') if c.strip()]
    return ', '.join(c.strip() for c in codes)


def permit_state(expiry, today):
    """'valid', 'expiring' (within 30 days) or 'expired' -- as
    driver_rules.permit_state, repeated here to keep this module standalone."""
    expiry = _as_date(expiry)
    if expiry is None or expiry < today:
        return 'expired'
    if (expiry - today).days <= 30:
        return 'expiring'
    return 'valid'


def permit_note(expiry, today):
    """'Expires in 12 days', 'Expires today', 'Expired 3 days ago'."""
    expiry = _as_date(expiry)
    if expiry is None:
        return 'No expiry date'
    left = (expiry - today).days
    if left > 1:
        return f'Expires in {left} days'
    if left == 1:
        return 'Expires tomorrow'
    if left == 0:
        return 'Expires today'
    ago = -left
    return f"Expired {ago} day{'s' if ago != 1 else ''} ago"


def _vehicle(imei, names):
    imei = _text(imei)
    return (names or {}).get(imei, imei) if imei else ''


def _sorted_drivers(drivers):
    return sorted(drivers, key=lambda d: _text(d.get('full_name')).lower())


# ── registry ─────────────────────────────────────────────────────────────────

def registry_row(driver, today, names=None):
    expiry = driver.get('permit_expiry')
    emergency = ' · '.join(p for p in (_text(driver.get('emergency_name')),
                                       _text(driver.get('emergency_phone'))) if p)
    return {
        'driver': _text(driver.get('full_name')),
        'phone': _text(driver.get('phone')),
        'employee_number': _text(driver.get('employee_number')),
        'national_id': _text(driver.get('national_id')),
        'permit_number': _text(driver.get('permit_number')),
        'permit_classes': _classes(driver.get('permit_classes')),
        'permit_expiry': day(expiry),
        'permit_status': PERMIT_LABELS[permit_state(expiry, today)],
        'ibutton_id': _text(driver.get('ibutton_id')),
        'home_branch': _text(driver.get('home_branch')),
        'current_vehicle': _vehicle(driver.get('current_imei'), names),
        'assigned_since': day(driver.get('assigned_at')),
        'status': STATUS_LABELS.get(driver.get('status'), _text(driver.get('status'))),
        'status_reason': _text(driver.get('status_reason')),
        'emergency_contact': emergency,
        'registered_on': day(driver.get('created_at')),
    }


def registry_rows(drivers, today, names=None):
    """{ALL_DRIVERS: [row, ...]} by name, or {} when there are none."""
    rows = [registry_row(d, today, names) for d in _sorted_drivers(drivers)]
    return {ALL_DRIVERS: rows} if rows else {}


# ── assignments ──────────────────────────────────────────────────────────────

def assignment_row(assignment, now, names=None):
    started, ended = assignment.get('assigned_at'), assignment.get('ended_at')
    current = ended is None
    return {
        'vehicle': _vehicle(assignment.get('device_imei'), names),
        'assigned_on': day(started),
        'assigned_time': clock(started),
        'released_on': '' if current else day(ended),
        'released_time': '' if current else clock(ended),
        'duration': duration(started, now if current else ended),
        'release_reason': 'Still assigned' if current else END_REASON_LABELS.get(
            assignment.get('end_reason'), _text(assignment.get('end_reason'))),
    }


def assignment_rows(drivers, assignments, now, names=None):
    """{driver name: [row, ...]} newest first, drivers by name, leaving out
    drivers with no assignment in the period. `assignments` are rows of
    dll_driver_assignments (driver_uid, device_imei, assigned_at, ended_at,
    end_reason)."""
    by_driver = {}
    for a in assignments:
        by_driver.setdefault(a.get('driver_uid'), []).append(a)
    out = {}
    for d in _sorted_drivers(drivers):
        held = sorted(by_driver.get(d.get('driver_uid'), ()),
                      key=lambda a: _as_datetime(a.get('assigned_at')) or datetime.min,
                      reverse=True)
        if held:
            out[_section_name(d, out)] = [assignment_row(a, now, names) for a in held]
    return out


def _section_name(driver, taken):
    """The driver's name, made unique if two drivers share it."""
    name = _text(driver.get('full_name')) or 'Unnamed driver'
    if name not in taken:
        return name
    extra = _text(driver.get('employee_number')) or _text(driver.get('phone'))
    return f'{name} ({extra})' if extra else f"{name} ({_text(driver.get('driver_uid'))[:8]})"


# ── compliance ───────────────────────────────────────────────────────────────

def compliance(driver, today):
    """(verdict, [problem, ...]) for one driver."""
    status = _text(driver.get('status')).lower()
    assigned = bool(_text(driver.get('current_imei')))
    state = permit_state(driver.get('permit_expiry'), today)
    serious, minor = [], []

    if state == 'expired':
        serious.append('Permit expired')
    elif state == 'expiring':
        minor.append('Permit ' + permit_note(driver.get('permit_expiry'), today).lower())

    if status in ('suspended', 'blacklisted'):
        label = STATUS_LABELS[status]
        if assigned:
            serious.append(f'{label} but still assigned to a vehicle')
        else:
            minor.append(label)

    missing = [label for field, label in OPTIONAL_DETAILS if not _text(driver.get(field))]
    if missing:
        minor.append('Missing: ' + ', '.join(missing))

    if status == 'inactive':
        verdict = INACTIVE
    elif serious:
        verdict = NON_COMPLIANT
    elif minor:
        verdict = NEEDS_ATTENTION
    else:
        verdict = COMPLIANT
    return verdict, serious + minor


def compliance_row(driver, today, names=None):
    verdict, problems = compliance(driver, today)
    expiry = driver.get('permit_expiry')
    return verdict, {
        'driver': _text(driver.get('full_name')),
        'phone': _text(driver.get('phone')),
        'permit_number': _text(driver.get('permit_number')),
        'permit_classes': _classes(driver.get('permit_classes')),
        'permit_expiry': day(expiry),
        'permit_status': PERMIT_LABELS[permit_state(expiry, today)],
        'permit_note': permit_note(expiry, today),
        'status': STATUS_LABELS.get(driver.get('status'), _text(driver.get('status'))),
        'current_vehicle': _vehicle(driver.get('current_imei'), names),
        'compliance': verdict,
        'issues': '; '.join(problems) if problems else 'None',
    }


def compliance_rows(drivers, today, names=None):
    """{verdict: [row, ...]} worst verdict first; within one, soonest permit
    expiry first. Empty verdicts are left out."""
    sections = {v: [] for v in VERDICTS}
    for d in sorted(drivers, key=lambda d: (_as_date(d.get('permit_expiry')) or date.min,
                                            _text(d.get('full_name')).lower())):
        verdict, row = compliance_row(d, today, names)
        sections[verdict].append(row)
    return {v: rows for v, rows in sections.items() if rows}


# ── fuel ─────────────────────────────────────────────────────────────────────

def fuel_row(issue, names=None, flag_labels=None, review_labels=None,
             payment_labels=None):
    """One fuel issue (fuel_rules.public_issue shape) for the driver report."""
    flag_labels = flag_labels or {}
    found = [f for f in issue.get('flags') or () if f.get('kind') == 'discrepancy']
    at = issue.get('issued_at')
    return {
        'date_logged': day(at),
        'time_logged': clock(at),
        'vehicle': _vehicle(issue.get('device_imei'), names),
        'fuel_type': _text(issue.get('fuel_type')).capitalize(),
        'litres': litres(issue.get('litres')),
        'unit_price': money(issue.get('unit_price')),
        'total_cost': money(issue.get('total_cost')),
        'payment_method': (payment_labels or {}).get(
            issue.get('payment_method'), _text(issue.get('payment_method'))),
        'receipt_number': _text(issue.get('receipt_number')),
        'station_name': _text(issue.get('station_name')),
        'flagged': '; '.join(flag_labels.get(f.get('code'), _text(f.get('message')))
                             for f in found) if found else 'No',
        'review': (review_labels or {}).get(issue.get('review_state'), ''),
    }


def fuel_rows(drivers, issues, names=None, flag_labels=None, review_labels=None,
              payment_labels=None):
    """{driver name: [row, ...]} newest first, drivers by name, leaving out
    voided issues and drivers with no fuel in the period."""
    by_driver = {}
    for issue in issues:
        if not issue.get('voided'):
            by_driver.setdefault(issue.get('driver_uid'), []).append(issue)
    out = {}
    for d in _sorted_drivers(drivers):
        got = sorted(by_driver.get(d.get('driver_uid'), ()),
                     key=lambda i: _text(i.get('issued_at')), reverse=True)
        if got:
            out[_section_name(d, out)] = [
                fuel_row(i, names, flag_labels, review_labels, payment_labels)
                for i in got]
    return out


# ── scorecard ────────────────────────────────────────────────────────────────

def scorecard_row(card):
    """One ranked scorecard (driver_scoring.scorecard + rank)."""
    score = card.get('score')
    breakdown = [f"{b['label']} x{b['count']} (-{b['deducted']})"
                 for b in card.get('breakdown') or () if b.get('count')]
    return {
        'rank': '' if card.get('rank') is None else str(card['rank']),
        'driver': _text(card.get('full_name')),
        'score': '' if score is None else str(score),
        'grade': (f"{card['grade']} - {card['grade_label']}" if card.get('grade')
                  else _text(card.get('grade_label'))),
        'violations': str(card.get('violation_count') or 0),
        'points_deducted': str(card.get('deducted') or 0),
        'breakdown': '; '.join(breakdown) if breakdown else 'None',
        'status': STATUS_LABELS.get(card.get('status'), _text(card.get('status'))),
    }


def scorecard_rows(cards):
    """{ALL_DRIVERS: [row, ...]} in rank order (driver_scoring.rank), or {}
    when there are no drivers."""
    rows = [scorecard_row(c) for c in cards]
    return {ALL_DRIVERS: rows} if rows else {}
