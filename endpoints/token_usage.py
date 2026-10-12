"""
token_usage -- daily token usage per service, from daily readings of the
running "used" totals (migration 049, dll_token_usage_daily).

A day's usage on one token account is its reading that day minus its reading
the day before. Some days cannot be worked out, and say so rather than
showing 0:

  * the first day an account was read (nothing to subtract from);
  * a day after a missed reading (the change spans several days);
  * a day the total went DOWN -- the account was reset or renewed, and what
    was used before the reset is not known.

Amounts in different billing units (hours, events, km, ...) are never added
together: every total is per unit.

It is pure, so tests/test_token_usage.py runs without a server. The routes
are in tokens_usage_routes.py.
"""

from datetime import timedelta

try:
    from . import token_values
except ImportError:                     # imported directly, by the tests
    import token_values

MAX_DAYS = 90


def reading(row):
    """(used, left) of a dll_user_token_accounts row as numbers, or
    (None, None) when used cannot be read. The units columns are the live
    ones; the hours columns are read only on accounts that never had units."""
    for used_col, left_col in (('token_used_units', 'token_units_left'),
                               ('token_hours_used', 'token_hours_left')):
        used, state = token_values.read(row.get(used_col))
        if state == token_values.NUMBER:
            left, left_state = token_values.read(row.get(left_col))
            return used, left if left_state == token_values.NUMBER else None
    return None, None


def daily(snapshots, today, days):
    """Usage for the `days` days ending `today`.

    snapshots  [{'account', 'service', 'unit', 'day': date, 'used': number}],
               one per account per day, any order; include the day before the
               window so its first day can be worked out
    Returns
      {'days': [{'day': date, 'by_service': {service: amount}, 'unknown': n}],
       'services': [{'service', 'unit', 'total', 'average_per_day',
                     'known_days'}],
       'units': {unit: total}, 'first_reading': date | None}
    oldest day first. `unknown` counts the accounts whose usage that day
    could not be worked out.
    """
    days = max(1, min(int(days), MAX_DAYS))
    window = [today - timedelta(days=n) for n in range(days - 1, -1, -1)]
    readings = {}
    labels = {}
    for s in snapshots:
        readings[(s['account'], s['day'])] = float(s['used'])
        labels[s['account']] = (s.get('service') or 'Other', s.get('unit') or 'unit')

    out_days = []
    totals = {}       # (service, unit) -> [total, known days]
    for day in window:
        by_service = {}
        unknown = 0
        for account, (service, unit) in labels.items():
            now_used = readings.get((account, day))
            if now_used is None:
                continue                      # not read that day
            before = readings.get((account, day - timedelta(days=1)))
            if before is None or now_used < before:
                unknown += 1
                continue
            amount = now_used - before
            by_service[service] = by_service.get(service, 0.0) + amount
            entry = totals.setdefault((service, unit), [0.0, set()])
            entry[0] += amount
            entry[1].add(day)
        out_days.append({'day': day, 'by_service': by_service, 'unknown': unknown})

    services = []
    units = {}
    for (service, unit), (total, known) in sorted(
            totals.items(), key=lambda item: -item[1][0]):
        services.append({'service': service, 'unit': unit, 'total': round(total, 2),
                         'average_per_day': round(total / len(known), 2),
                         'known_days': len(known)})
        units[unit] = round(units.get(unit, 0.0) + total, 2)

    first = min((s['day'] for s in snapshots), default=None)
    return {'days': out_days, 'services': services, 'units': units,
            'first_reading': first}
