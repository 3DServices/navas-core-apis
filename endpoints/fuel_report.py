"""
fuel_report -- the rows of the three FuelMath reports
(POST /data-stream/reports/fuel/<kind>/generate-data, fuel_registry.py).

  issuance     every fuel issue: who, how much, what it cost, how it was paid
  consumption  every full tank that closed a measured span: km, litres, km/L
               against the vehicle's expected km/L, and what the excess cost
  exceptions   every issue a check flagged, with what was found and how the
               review ended

All three are built from FuelMath records (fuel_rules.public_issue()), not
from a fuel sensor, so they work for every vehicle. Voided issues are left
out: they are kept for the record, not counted.

Rows use the field names the app's report table, PDF and Excel read, and the
values are text as the app shows them. Money is whole shillings with
thousands separators; the app's number reader ignores the separators.

Pure -- no Flask, no database -- so tests/test_fuel_report.py runs without a
server.
"""

from datetime import datetime

KINDS = ('issuance', 'consumption', 'exceptions')

EMPTY_MESSAGES = {
    'issuance': 'No Fuel Issues Found for the selected vehicles and dates',
    'consumption': 'No Fuel Consumption Data Found: consumption is measured '
                   'between two full tanks',
    'exceptions': 'No Fuel Exceptions Found for the selected vehicles and dates',
}

# Short names for the discrepancies, as the app's rule form shows them.
FLAG_LABELS = {
    'over_capacity': 'More than the tank holds',
    'more_than_used': 'More than the distance needs',
    'not_stopped': 'Vehicle not stopped',
    'odometer_backwards': 'Odometer went backwards',
    'odometer_mismatch': 'Odometer does not match tracker',
    'driver_not_assigned': 'Driver not assigned',
    'driver_not_allowed': 'Driver not allowed to drive',
    'possible_duplicate': 'Possible duplicate',
    'fuel_type_mismatch': 'Wrong fuel type',
}

REVIEW_LABELS = {
    'none': 'OK', 'open': 'Needs review', 'explained': 'Explained',
    'confirmed_loss': 'Confirmed loss',
}

PAYMENT_LABELS = {
    'cash': 'Cash', 'fuel_card': 'Fuel card', 'credit': 'Credit',
    'mobile_money': 'Mobile money',
}


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


def one_decimal(value):
    n = _num(value)
    return '' if n is None else f'{n:.1f}'


def _when(issue):
    at = issue.get('issued_at')
    if isinstance(at, str):
        try:
            at = datetime.fromisoformat(at.strip().replace(' ', 'T'))
        except ValueError:
            return '', ''
    if not hasattr(at, 'strftime'):
        return '', ''
    return at.strftime('%Y-%m-%d'), at.strftime('%H:%M')


def _driver(issue):
    return str(issue.get('driver_name') or issue.get('driver_uid') or '')


def discrepancies(issue):
    return [f for f in issue.get('flags') or () if f.get('kind') == 'discrepancy']


def issuance_row(issue):
    day, clock = _when(issue)
    return {
        'date_logged': day,
        'time_logged': clock,
        'driver': _driver(issue),
        'fuel_type': str(issue.get('fuel_type') or '').capitalize(),
        'litres': litres(issue.get('litres')),
        'unit_price': money(issue.get('unit_price')),
        'total_cost': money(issue.get('total_cost')),
        'payment_method': PAYMENT_LABELS.get(issue.get('payment_method'),
                                             str(issue.get('payment_method') or '')),
        'receipt_number': str(issue.get('receipt_number') or ''),
        'station_name': str(issue.get('station_name') or ''),
        'full_tank': 'Yes' if issue.get('full_tank') else 'No',
        'review': REVIEW_LABELS.get(issue.get('review_state'), ''),
    }


def consumption_row(issue, profile=None):
    """A full tank that closed a measured span, or None when it did not."""
    km = _num(issue.get('km_since_full'))
    used = _num(issue.get('litres_since_full'))
    if not issue.get('full_tank') or not km or not used:
        return None
    price = _num(issue.get('unit_price')) or 0
    baseline = _num((profile or {}).get('baseline_km_per_l'))
    expected_l = km / baseline if baseline else None
    excess_l = max(0.0, used - expected_l) if expected_l is not None else None
    day, _ = _when(issue)
    return {
        'date_logged': day,
        'driver': _driver(issue),
        'km_since_full': one_decimal(km),
        'litres_since_full': litres(used),
        'km_per_l': f'{km / used:.2f}',
        'expected_km_per_l': '' if baseline is None else f'{baseline:g}',
        'excess_litres': '' if excess_l is None else litres(excess_l),
        'excess_cost': '' if excess_l is None else money(excess_l * price),
        'cost_per_km': money(used * price / km) if price else '',
    }


def exception_row(issue):
    """An issue a check flagged, or None when nothing was found."""
    found = discrepancies(issue)
    if not found:
        return None
    day, clock = _when(issue)
    return {
        'date_logged': day,
        'time_logged': clock,
        'driver': _driver(issue),
        'litres': litres(issue.get('litres')),
        'total_cost': money(issue.get('total_cost')),
        'problems': '; '.join(FLAG_LABELS.get(f.get('code'), str(f.get('message') or ''))
                              for f in found),
        'review': REVIEW_LABELS.get(issue.get('review_state'), ''),
        'review_note': str(issue.get('review_note') or ''),
    }


def rows_for(kind, issues, profiles=None):
    """{device_imei: [row, ...]} for one report, newest first, leaving out
    voided issues and vehicles with nothing to show.

    issues    public_issue() dicts
    profiles  {device_imei: profile row} (consumption only)
    """
    profiles = profiles or {}
    ordered = sorted((i for i in issues if not i.get('voided')),
                     key=lambda i: str(i.get('issued_at') or ''), reverse=True)
    out = {}
    for issue in ordered:
        imei = str(issue.get('device_imei') or '')
        if kind == 'issuance':
            row = issuance_row(issue)
        elif kind == 'consumption':
            row = consumption_row(issue, profiles.get(imei))
        elif kind == 'exceptions':
            row = exception_row(issue)
        else:
            raise ValueError(kind)
        if row is not None:
            out.setdefault(imei, []).append(row)
    return out
