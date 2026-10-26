"""
geofence_report -- the arithmetic of the Geofence Entry and Geofence Exit
reports (POST /data-stream/reports/geozone/generate-data).

The OLIWA app offers the two as separate report types, so a client can pull
just the entries, or just the exits. The route reads the geofence crossings
the alert engine records in dll_event_notifications (one row per crossing,
breach_type 'enter' or 'exit'); this module turns the request's `breach` into
the breach_type values to match, and a row into what the app shows.

It used to read dll_triggered_events, which holds no rows at all in
production, and could not tell an entry from an exit except by parsing a
free-text value.

Pure -- no Flask, no database -- so tests/test_geofence_report.py runs
without a server.
"""

# breach_type values that mean each direction. The alert engine writes
# 'enter' / 'exit'; the console's older /notifications/log rows are not as
# consistent, so the common spellings are accepted too.
ENTRY_VALUES = ('enter', 'entry', 'entrance', 'in', 'inside')
EXIT_VALUES = ('exit', 'out', 'outside', 'leave', 'left')


def breach_values(breach):
    """The breach_type values (lower case) a request's `breach` selects:
    'entry' or 'exit' (any case, 'enter'/'entrance' too), or None for both
    directions -- what the endpoint returned before the split."""
    b = str(breach or '').strip().lower()
    if b in ENTRY_VALUES:
        return ENTRY_VALUES
    if b in EXIT_VALUES:
        return EXIT_VALUES
    return None


def direction(breach_type):
    """'Entry', 'Exit', or the stored text when it is neither."""
    b = str(breach_type or '').strip().lower()
    if b in ENTRY_VALUES:
        return 'Entry'
    if b in EXIT_VALUES:
        return 'Exit'
    return str(breach_type or '')


def row(date_triggered, geozone_name, breach_type, rule_name):
    """One report row, in the field names the app's report table reads."""
    when = date_triggered
    return {
        'date_logged': when.strftime('%Y-%m-%d') if when else '',
        'time_logged': when.strftime('%H:%M:%S') if when else '',
        'geozone_name': str(geozone_name or 'Unknown zone'),
        'event_triggered': direction(breach_type),
        'rule_name': str(rule_name or ''),
    }


def empty_message(breach):
    """What to answer when nothing matched -- the app shows "No data"."""
    values = breach_values(breach)
    if values is ENTRY_VALUES:
        return 'No Geofence Entries Found'
    if values is EXIT_VALUES:
        return 'No Geofence Exits Found'
    return 'No Geozone Events Found'
