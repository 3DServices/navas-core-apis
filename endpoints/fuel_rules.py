"""
fuel_rules -- FuelMath: what a fuel issue must hold, and how it is checked
against what the tracker saw. Routes in fuel_registry.py; tables in
migration 053.

Pure: no Flask, no database, no clock (`now` is passed in), so
tests/test_fuel_rules.py runs without a server.

A fuel issue
  Required    device_imei, issued_at, litres, unit_price, station_name,
              payment_method, fuel_type (taken from the vehicle's profile
              when it has one)
  Optional    driver_uid (when left out, fuel_registry uses whoever was
              assigned to the vehicle at issued_at, if anyone), full_tank,
              odometer_km, receipt_number, notes (the receipt photo is
              uploaded separately)
  total_cost  litres x unit_price, worked out here -- UGX, whole shillings

The checks (assess)
  Every issue is checked when it is recorded, from the tracker's positions
  and the vehicle's fuel profile. A check that finds a problem is a
  DISCREPANCY flag and opens a review; one that could not be done is a
  NOTICE and opens nothing.

  Consumption is measured fill-to-fill: between two full tanks, the litres
  issued (every issue after the first full tank, up to and including the
  second) against the kilometres the tracker measured. A partial issue is
  checked the same way against the distance since the last full tank -- a
  vehicle cannot take in more fuel than it has burned since it was full.
"""

import re
from datetime import date, datetime, timedelta
from math import asin, cos, radians, sin, sqrt

try:
    from . import driver_rules
except ImportError:                        # tests import this file directly
    import driver_rules

FUEL_TYPES = ('petrol', 'diesel')
PAYMENT_METHODS = ('cash', 'fuel_card', 'credit', 'mobile_money')
REVIEW_OUTCOMES = ('explained', 'confirmed_loss')

LITRES_MAX = 1000
PRICE_MIN, PRICE_MAX = 100, 50000          # UGX per litre
ODOMETER_MAX = 2000000
STATION_MAX = 120
RECEIPT_MAX = 60
NOTES_MAX = 1000
TANK_MAX = 2000
BASELINE_MAX = 50                          # km per litre
TOLERANCE_DEFAULT = 20                     # percent
TOLERANCE_MIN, TOLERANCE_MAX = 5, 50

# How far back an issue may be recorded, and how far ahead of the server's
# clock (a phone a few minutes fast).
BACKDATE_MAX = timedelta(days=92)
FUTURE_SLACK = timedelta(minutes=10)

# The vehicle must have stopped within this long of the time on the receipt:
# times are typed from a receipt, or remembered, so they are not exact.
STOP_WINDOW = timedelta(minutes=45)
STOP_RADIUS_M = 60
STOP_MIN = timedelta(minutes=2)
# Positions are read this far either side of the window, so a tracker that
# was quiet while parked (ignition off) still shows the stop.
READ_MARGIN = timedelta(hours=2)

# Fill-to-fill is measured over at most this long. The busiest unit writes
# about 13,000 fixes a day; three weeks of them is as much as one request
# should read.
FILL_SPAN_MAX = timedelta(days=21)

# Small top-ups are within the error of a fuel gauge and a pump: this many
# litres over the expected amount is not flagged.
USAGE_MARGIN_L = 5.0
OVER_CAPACITY = 1.05
DUPLICATE_WINDOW = timedelta(minutes=30)

# The trip playback filters, so FuelMath and Trip Playback measure the same
# distance: GPS jitter under 15 m is not movement, and a jump faster than
# 250 km/h is a bad fix.
JITTER_M = 15
TELEPORT_KMH = 250

EARTH_RADIUS_KM = 6371.0088

# code -> (kind, message). 'discrepancy' opens a review; 'notice' does not.
FLAGS = {
    'over_capacity': ('discrepancy', 'More litres than the tank holds.'),
    'more_than_used': ('discrepancy',
                       'More fuel than the distance driven since the last '
                       'full tank needs.'),
    'not_stopped': ('discrepancy',
                    'The tracker shows the vehicle was not stopped around '
                    'this time.'),
    'odometer_backwards': ('discrepancy',
                           'The odometer is lower than at the previous issue.'),
    'odometer_mismatch': ('discrepancy',
                          'The odometer distance does not match the tracker '
                          'distance.'),
    'driver_not_assigned': ('discrepancy',
                            'Another driver was assigned to this vehicle at '
                            'that time.'),
    'driver_not_allowed': ('discrepancy',
                           'The driver was not allowed to drive at that time.'),
    'possible_duplicate': ('discrepancy',
                           'Another issue for this vehicle within 30 minutes.'),
    'fuel_type_mismatch': ('discrepancy',
                           "Not the fuel type in the vehicle's profile."),
    'no_driver': ('notice',
                  'No driver was recorded, and nobody was assigned to the '
                  'vehicle at that time.'),
    'no_tracker_data': ('notice',
                        'The tracker sent nothing around this time, so the '
                        'issue could not be checked against it.'),
    'tracker_unavailable': ('notice',
                            'Tracker data could not be read, so the issue was '
                            'not checked against it.'),
    'no_profile': ('notice',
                   'This vehicle has no fuel profile, so tank size and '
                   'consumption were not checked.'),
    'first_full_tank': ('notice',
                        'No earlier full tank: consumption is measured from '
                        'the next full tank.'),
    'span_too_long': ('notice',
                      'More than 21 days since the last full tank, so '
                      'consumption was not checked.'),
}


def _text(value):
    return re.sub(r'\s+', ' ', str(value or '')).strip()


def _number(value):
    """A number from the app ('45.5', 45.5, '12,500'), or None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = _text(value).replace(',', '')
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _flag(value):
    if isinstance(value, bool):
        return value
    return _text(value).lower() in ('1', 'true', 'yes', 'on')


def parse_datetime(value):
    """'2026-10-28T08:30', '2026-10-28 08:30:15' (or a datetime) -> naive
    local datetime, seconds kept; None when it will not parse. A trailing
    offset is not accepted: the app sends local (EAT) time."""
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    text = _text(value).replace('T', ' ')
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d %H:%M:%S.%f'):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def total_cost(litres, unit_price):
    """UGX has no cents: the receipt total, to the shilling."""
    return float(round(litres * unit_price))


# ── validation ───────────────────────────────────────────────────────────────

def validate_profile(data):
    """A vehicle's fuel profile. Returns (clean, errors)."""
    data = data or {}
    clean, errors = {}, {}

    fuel = _text(data.get('fuel_type')).lower()
    if fuel not in FUEL_TYPES:
        errors['fuel_type'] = 'Choose petrol or diesel.'
    else:
        clean['fuel_type'] = fuel

    tank = _number(data.get('tank_capacity_l'))
    if tank is None or not 0 < tank <= TANK_MAX:
        errors['tank_capacity_l'] = f'Enter the tank size in litres (1 to {TANK_MAX}).'
    else:
        clean['tank_capacity_l'] = round(tank, 1)

    baseline = _number(data.get('baseline_km_per_l'))
    if baseline is None or not 0 < baseline <= BASELINE_MAX:
        errors['baseline_km_per_l'] = (
            f'Enter the expected km per litre (more than 0, at most {BASELINE_MAX}).')
    else:
        clean['baseline_km_per_l'] = round(baseline, 2)

    raw = data.get('tolerance_pct')
    if raw is None or _text(raw) == '':
        clean['tolerance_pct'] = TOLERANCE_DEFAULT
    else:
        tolerance = _number(raw)
        if tolerance is None or not TOLERANCE_MIN <= tolerance <= TOLERANCE_MAX \
                or tolerance != int(tolerance):
            errors['tolerance_pct'] = (
                f'Tolerance is a whole percent, {TOLERANCE_MIN} to {TOLERANCE_MAX}.')
        else:
            clean['tolerance_pct'] = int(tolerance)
    return clean, errors


def validate_issue(data, now, profile_fuel=None):
    """A fuel issue from the app. `now` is the local time on the server;
    `profile_fuel` the vehicle's profile fuel type, used when none is sent.
    Returns (clean, errors)."""
    data = data or {}
    clean, errors = {}, {}

    imei = ''.join(str(data.get('device_imei') or '').split())
    if not imei:
        errors['device_imei'] = 'Choose a vehicle.'
    else:
        clean['device_imei'] = imei

    # Optional: fuel for a vehicle nobody is assigned to is still fuel.
    clean['driver_uid'] = _text(data.get('driver_uid')) or None

    issued_at = parse_datetime(data.get('issued_at'))
    if issued_at is None:
        errors['issued_at'] = 'Enter the date and time the fuel was issued.'
    elif issued_at > now + FUTURE_SLACK:
        errors['issued_at'] = 'The issue time is in the future.'
    elif issued_at < now - BACKDATE_MAX:
        errors['issued_at'] = 'Issues older than 92 days cannot be recorded.'
    else:
        clean['issued_at'] = issued_at

    litres = _number(data.get('litres'))
    if litres is None or not 0 < litres <= LITRES_MAX:
        errors['litres'] = f'Enter the litres issued (more than 0, at most {LITRES_MAX}).'
    else:
        clean['litres'] = round(litres, 2)

    price = _number(data.get('unit_price'))
    if price is None or not PRICE_MIN <= price <= PRICE_MAX:
        errors['unit_price'] = (
            f'Enter the price per litre in UGX ({PRICE_MIN:,} to {PRICE_MAX:,}).')
    else:
        clean['unit_price'] = round(price, 2)

    fuel = _text(data.get('fuel_type')).lower() or (profile_fuel or '')
    if fuel not in FUEL_TYPES:
        errors['fuel_type'] = 'Choose petrol or diesel.'
    else:
        clean['fuel_type'] = fuel

    station = _text(data.get('station_name'))
    if len(station) < 2 or len(station) > STATION_MAX:
        errors['station_name'] = f'Enter the station name (2 to {STATION_MAX} characters).'
    else:
        clean['station_name'] = station

    method = _text(data.get('payment_method')).lower()
    if method not in PAYMENT_METHODS:
        errors['payment_method'] = 'Choose how the fuel was paid for.'
    else:
        clean['payment_method'] = method

    clean['full_tank'] = _flag(data.get('full_tank'))

    raw = data.get('odometer_km')
    if raw is None or _text(raw) == '':
        clean['odometer_km'] = None
    else:
        odometer = _number(raw)
        if odometer is None or not 0 <= odometer <= ODOMETER_MAX:
            errors['odometer_km'] = 'Enter the odometer reading in km.'
        else:
            clean['odometer_km'] = round(odometer, 1)

    receipt = _text(data.get('receipt_number')).upper()
    if len(receipt) > RECEIPT_MAX:
        errors['receipt_number'] = f'At most {RECEIPT_MAX} characters.'
    else:
        clean['receipt_number'] = receipt or None

    notes = str(data.get('notes') or '').strip()
    if len(notes) > NOTES_MAX:
        errors['notes'] = f'At most {NOTES_MAX} characters.'
    else:
        clean['notes'] = notes or None

    if 'litres' in clean and 'unit_price' in clean:
        clean['total_cost'] = total_cost(clean['litres'], clean['unit_price'])
    return clean, errors


# ── positions ────────────────────────────────────────────────────────────────

def distance_m(a, b):
    """Great-circle metres between two fixes ({'lat', 'lon'})."""
    lat1, lon1, lat2, lon2 = (radians(v) for v in (a['lat'], a['lon'], b['lat'], b['lon']))
    h = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_KM * 1000 * asin(min(1.0, sqrt(h)))


def _ordered(points):
    return sorted((p for p in points if p.get('at') is not None), key=lambda p: p['at'])


def track_km(points, start=None, end=None):
    """Kilometres driven along the fixes between start and end (either may be
    None). Movement under JITTER_M is ignored, and a fix that would mean more
    than TELEPORT_KMH is skipped as a bad fix."""
    total, anchor = 0.0, None
    for p in _ordered(points):
        if (start and p['at'] < start) or (end and p['at'] > end):
            continue
        if anchor is None:
            anchor = p
            continue
        metres = distance_m(anchor, p)
        if metres < JITTER_M:
            continue
        hours = (p['at'] - anchor['at']).total_seconds() / 3600
        if hours <= 0 or metres / 1000 / hours > TELEPORT_KMH:
            continue
        total += metres / 1000
        anchor = p
    return total


def find_stop(points, start, end):
    """The fix nearest the middle of [start, end] of a stop that overlaps it:
    the vehicle stayed within STOP_RADIUS_M for at least STOP_MIN. A tracker
    that sent nothing while parked still shows the stop, as two fixes at the
    same place minutes apart. None when the vehicle did not stop."""
    seq = _ordered(points)
    middle = start + (end - start) / 2
    best = None
    i = 0
    while i < len(seq):
        j = i
        while j + 1 < len(seq) and distance_m(seq[i], seq[j + 1]) <= STOP_RADIUS_M:
            j += 1
        first, last = seq[i], seq[j]
        if last['at'] - first['at'] >= STOP_MIN and \
                first['at'] <= end and last['at'] >= start:
            run = seq[i:j + 1]
            near = min(run, key=lambda p: abs(p['at'] - middle))
            if best is None or abs(near['at'] - middle) < abs(best['at'] - middle):
                best = near
            i = j + 1
        else:
            i += 1
    return best


def nearest_fix(points, at, within):
    inside = [p for p in points if p.get('at') is not None and abs(p['at'] - at) <= within]
    return min(inside, key=lambda p: abs(p['at'] - at)) if inside else None


# ── assessment ───────────────────────────────────────────────────────────────

def assess(issue, *, profile=None, previous_full=None, since_full=(),
           previous_odometer=None, points=None, driver=None,
           assigned_driver_uid=None, nearby_issues=0):
    """Check one issue. Everything it needs is passed in:

    issue              the clean issue (validate_issue)
    profile            the vehicle's fuel profile, or None
    previous_full      the latest earlier full-tank issue {issue_uid,
                       issued_at}, or None
    since_full         earlier issues after previous_full: [{litres}]
    previous_odometer  the latest earlier issue with an odometer reading
                       {issued_at, odometer_km}, or None
    points             the tracker's fixes [{lat, lon, at, place}] from
                       previous_full (or issued_at - READ_MARGIN) to issued_at
                       + READ_MARGIN; None when they could not be read
    driver             the driver {status, permit_expiry}
    assigned_driver_uid who was assigned to the vehicle at issued_at, if
                       anyone
    nearby_issues      other issues for the vehicle within DUPLICATE_WINDOW

    Returns the columns to store: tracker_state, tracker_lat/lon/at/place,
    km_since_full, litres_since_full, km_per_l, previous_full_uid, flags (a
    list of codes) and review_state.
    """
    at = issue['issued_at']
    litres = issue['litres']
    flags = []
    out = {'tracker_state': 'unchecked', 'tracker_lat': None, 'tracker_lon': None,
           'tracker_at': None, 'tracker_place': None, 'km_since_full': None,
           'litres_since_full': None, 'km_per_l': None,
           'previous_full_uid': previous_full['issue_uid'] if previous_full else None}

    # ── the vehicle ──
    if profile is None:
        flags.append('no_profile')
    else:
        if litres > float(profile['tank_capacity_l']) * OVER_CAPACITY:
            flags.append('over_capacity')
        if issue['fuel_type'] != profile['fuel_type']:
            flags.append('fuel_type_mismatch')

    # ── the driver ──
    if driver is not None:
        if driver_rules.assignment_refusal(
                driver.get('status'), driver.get('permit_expiry'), at.date()):
            flags.append('driver_not_allowed')
    if not issue.get('driver_uid'):
        flags.append('no_driver')
    elif assigned_driver_uid and assigned_driver_uid != issue['driver_uid']:
        flags.append('driver_not_assigned')
    if nearby_issues:
        flags.append('possible_duplicate')

    # ── the odometer, against the previous reading ──
    odometer = issue.get('odometer_km')
    if odometer is not None and previous_odometer is not None:
        before = float(previous_odometer['odometer_km'])
        if odometer < before:
            flags.append('odometer_backwards')
        elif points:
            covered = min((p['at'] for p in points if p.get('at')), default=None)
            if covered is not None and covered <= previous_odometer['issued_at'] + READ_MARGIN:
                tracked = track_km(points, previous_odometer['issued_at'], at)
                if abs((odometer - before) - tracked) > max(20.0, tracked * 0.15):
                    flags.append('odometer_mismatch')

    # ── the tracker: was the vehicle stopped, and how far has it gone ──
    if points is None:
        out['tracker_state'] = 'unavailable'
        flags.append('tracker_unavailable')
    else:
        stop = find_stop(points, at - STOP_WINDOW, at + STOP_WINDOW)
        fix = stop or nearest_fix(points, at, STOP_WINDOW)
        if fix is None:
            out['tracker_state'] = 'no_data'
            flags.append('no_tracker_data')
        else:
            out['tracker_state'] = 'checked'
            out.update(tracker_lat=fix['lat'], tracker_lon=fix['lon'],
                       tracker_at=fix['at'], tracker_place=fix.get('place'))
            if stop is None:
                flags.append('not_stopped')

        if previous_full is None:
            flags.append('first_full_tank')
        elif at - previous_full['issued_at'] > FILL_SPAN_MAX:
            flags.append('span_too_long')
        elif out['tracker_state'] == 'checked':
            km = track_km(points, previous_full['issued_at'], at)
            used = litres + sum(float(i['litres']) for i in since_full)
            out['km_since_full'] = round(km, 1)
            out['litres_since_full'] = round(used, 2)
            if issue.get('full_tank') and used > 0:
                out['km_per_l'] = round(km / used, 2)
            if profile is not None:
                baseline = float(profile['baseline_km_per_l'])
                tolerance = int(profile['tolerance_pct']) / 100
                expected = km / baseline
                if used > expected * (1 + tolerance) + USAGE_MARGIN_L:
                    flags.append('more_than_used')

    out['flags'] = flags
    out['review_state'] = review_state_for(flags)
    return out


def review_state_for(flags):
    return 'open' if any(FLAGS.get(f, ('notice',))[0] == 'discrepancy'
                         for f in flags) else 'none'


def review_refusal(current, outcome, voided):
    """Why a review may not be closed with `outcome`, or None."""
    if voided:
        return 'This issue was voided.'
    if outcome not in REVIEW_OUTCOMES:
        return 'Choose: explained, or confirmed loss.'
    if current == 'none':
        return 'This issue has nothing to review.'
    return None


# ── what the app receives ────────────────────────────────────────────────────

def _iso(value):
    return value.isoformat() if isinstance(value, (date, datetime)) else None


def _float(value):
    return float(value) if value is not None else None


def flag_list(text):
    codes = [c for c in str(text or '').split(',') if c]
    return [{'code': c, 'kind': FLAGS.get(c, ('notice', c))[0],
             'message': FLAGS.get(c, ('notice', c))[1]} for c in codes]


def public_issue(row):
    """A stored issue (dict of columns) as the app receives it."""
    return {
        'issue_uid': row.get('issue_uid'),
        'device_imei': row.get('device_imei'),
        'driver_uid': row.get('driver_uid'),
        'driver_name': row.get('driver_name'),
        'issued_at': _iso(row.get('issued_at')),
        'fuel_type': row.get('fuel_type'),
        'litres': _float(row.get('litres')),
        'unit_price': _float(row.get('unit_price')),
        'total_cost': _float(row.get('total_cost')),
        'full_tank': bool(row.get('full_tank')),
        'odometer_km': _float(row.get('odometer_km')),
        'station_name': row.get('station_name'),
        'receipt_number': row.get('receipt_number'),
        'payment_method': row.get('payment_method'),
        'notes': row.get('notes'),
        'has_receipt': bool(row.get('receipt_file')),
        'tracker': {
            'state': row.get('tracker_state'),
            'lat': row.get('tracker_lat'),
            'lon': row.get('tracker_lon'),
            'at': _iso(row.get('tracker_at')),
            'place': row.get('tracker_place'),
        },
        'km_since_full': _float(row.get('km_since_full')),
        'litres_since_full': _float(row.get('litres_since_full')),
        'km_per_l': _float(row.get('km_per_l')),
        'flags': flag_list(row.get('flags')),
        'review_state': row.get('review_state'),
        'review_note': row.get('review_note'),
        'reviewed_by': row.get('reviewed_by'),
        'reviewed_at': _iso(row.get('reviewed_at')),
        'voided': row.get('voided_at') is not None,
        'voided_at': _iso(row.get('voided_at')),
        'void_reason': row.get('void_reason'),
        'issued_by': row.get('issued_by'),
        'created_at': _iso(row.get('created_at')),
    }


def public_profile(row):
    return {
        'device_imei': row.get('device_imei'),
        'fuel_type': row.get('fuel_type'),
        'tank_capacity_l': _float(row.get('tank_capacity_l')),
        'baseline_km_per_l': _float(row.get('baseline_km_per_l')),
        'tolerance_pct': row.get('tolerance_pct'),
        'updated_at': _iso(row.get('updated_at')),
    }


def summarise(issues, profiles):
    """Totals for a period from its (non-voided) issues.

    Measured consumption counts only full-tank issues that carry km_per_l --
    each one closes a fill-to-fill interval. excess_litres is what those
    intervals used beyond the baseline, and excess_cost the same in UGX at
    the vehicle's average price: the figure a fleet manager acts on.
    """
    vehicles, drivers = {}, {}
    for row in issues:
        imei = row['device_imei']
        v = vehicles.setdefault(imei, {
            'device_imei': imei, 'issues': 0, 'litres': 0.0, 'cost': 0.0,
            'open_reviews': 0, 'flagged': 0, 'measured_km': 0.0,
            'measured_litres': 0.0})
        # Issues with no driver are one bucket, so the drivers still add
        # up to the period's totals.
        d = drivers.setdefault(row.get('driver_uid'), {
            'driver_uid': row.get('driver_uid'),
            'driver_name': (row.get('driver_name') if row.get('driver_uid')
                            else 'No driver recorded'),
            'issues': 0, 'litres': 0.0, 'cost': 0.0, 'flagged': 0})
        litres, cost = float(row['litres']), float(row['total_cost'])
        flagged = review_state_for(str(row.get('flags') or '').split(',')) == 'open'
        for bucket in (v, d):
            bucket['issues'] += 1
            bucket['litres'] += litres
            bucket['cost'] += cost
            bucket['flagged'] += 1 if flagged else 0
        if row.get('review_state') == 'open':
            v['open_reviews'] += 1
        if row.get('full_tank') and row.get('km_per_l') is not None:
            v['measured_km'] += float(row['km_since_full'] or 0)
            v['measured_litres'] += float(row['litres_since_full'] or 0)

    for imei, v in vehicles.items():
        profile = profiles.get(imei)
        price = v['cost'] / v['litres'] if v['litres'] else 0.0
        v['avg_price'] = round(price, 2)
        v['km_per_l'] = (round(v['measured_km'] / v['measured_litres'], 2)
                         if v['measured_litres'] else None)
        v['cost_per_km'] = (round(price * v['measured_litres'] / v['measured_km'], 2)
                            if v['measured_km'] else None)
        v['baseline_km_per_l'] = (float(profile['baseline_km_per_l'])
                                  if profile else None)
        excess = None
        if profile and v['measured_litres']:
            excess = max(0.0, v['measured_litres']
                         - v['measured_km'] / float(profile['baseline_km_per_l']))
        v['excess_litres'] = round(excess, 1) if excess is not None else None
        v['excess_cost'] = round(excess * price) if excess is not None else None
        for key in ('litres', 'measured_km', 'measured_litres'):
            v[key] = round(v[key], 1)
        v['cost'] = round(v['cost'])
    for d in drivers.values():
        d['litres'] = round(d['litres'], 1)
        d['cost'] = round(d['cost'])

    totals = {
        'issues': sum(v['issues'] for v in vehicles.values()),
        'litres': round(sum(v['litres'] for v in vehicles.values()), 1),
        'cost': sum(v['cost'] for v in vehicles.values()),
        'open_reviews': sum(v['open_reviews'] for v in vehicles.values()),
        'excess_cost': sum(v['excess_cost'] or 0 for v in vehicles.values()),
    }
    by_cost = lambda x: -x['cost']             # noqa: E731
    return {'totals': totals,
            'vehicles': sorted(vehicles.values(), key=by_cost),
            'drivers': sorted(drivers.values(), key=by_cost)}


RECEIPT_MAX_BYTES = 5 * 1024 * 1024

# Unique-index name -> the field the client is told is a duplicate.
DUPLICATE_FIELDS = {
    'uq_fuel_receipt': ('receipt_number',
                        'This receipt number is already recorded.'),
}


# ── Fuel sensors ─────────────────────────────────────────────────────────────
# A vehicle has a fuel sensor when its device config names a 'fuel_level'
# input. Analogue sensors (these IO sources) report millivolts and need the
# unit's calibration table (dll_calibrated_fuel_data) to become litres, as
# data.py's fuel calculator does; the others report litres directly.
CALIBRATED_SOURCES = ('270', '12', '201')
_NO_SOURCE = ('', '0', 'none', 'null', 'n/a', 'na', '-', 'no', 'false', 'no_data')


def sensor_state(source, calibrated):
    """'none', 'needs_calibration' or 'ready' for one vehicle.

    source      the 'fuel_level' config's data source, or None when the unit
                has no such config
    calibrated  the unit has a calibration table
    """
    text = str(source if source is not None else '').strip().lower()
    if text in _NO_SOURCE:
        return 'none'
    if text in CALIBRATED_SOURCES and not calibrated:
        return 'needs_calibration'
    return 'ready'
