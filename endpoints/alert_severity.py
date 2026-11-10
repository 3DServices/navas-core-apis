"""
alert_severity -- how urgent an alert is: critical, warning or info.

dll_event_notifications has no severity of its own. It is worked out when the
alerts are read (GET /notifications/<owner_uid>/list), from what the alert
says it is, so every alert has one -- including the ones raised before this
module existed -- and nothing that writes alerts has to change.

    critical  somebody or something may be in danger, or the unit is being
              interfered with: SOS / panic, tamper, power cut, theft, crash,
              towing, jamming
              -- and entering a geofence marked restricted (migration 048)
    warning   needs attention: speeding and harsh driving, geofence breaches,
              fuel, offline units, low battery, low token balance, a failed
              top-up -- and any rule this module does not recognise
    info      for the record: ignition on/off, top-up and renewal receipts,
              usage, reports

It is pure, so tests/test_alert_severity.py runs without a server.
"""

import re

SEVERITIES = ('critical', 'warning', 'info')

# Checked in order: the first group with a match wins, so "fuel theft" is
# critical and "top-up failed" a warning.
_RULES = (
    ('critical', (r'\bsos\b', r'panic', r'tamper', r'power cut',
                  r'power (?:loss|lost|disconnect)', r'theft',
                  r'stolen', r'crash', r'accident', r'collision', r'\btow',
                  r'jamm', r'unauthori[sz]ed')),
    ('warning', (r'speed', r'harsh', r'brak', r'accel', r'corner',
                 r'geofence', r'fuel', r'offline', r'no signal', r'battery',
                 r'low balance', r'running low', r'fail', r'limit reached',
                 r'idl', r'overdue', r'expir')),
    ('info', (r'ignition', r'top up', r'renew', r'usage', r'report',
              r'receipt', r'preview', r'approve')),
)
_COMPILED = tuple((level, tuple(re.compile(p) for p in patterns))
                  for level, patterns in _RULES)

# Anything unrecognised: a rule somebody set up deserves a look.
DEFAULT = 'warning'


def _text(*parts):
    """Lower-case, with '_' and '-' read as spaces ('low_balance' is
    'low balance', 'top-up' is 'top up')."""
    joined = ' '.join(str(p or '') for p in parts).lower()
    return re.sub(r'[_\-]+', ' ', joined)


def severity_of(event_name='', condition='', trigger_value='', breach_type='',
                zone_category=''):
    """One of SEVERITIES for a dll_event_notifications row.

    A geofence alert's trigger_value is 'entry:<zone name>', and a zone
    called "Tow yard" must not make a crossing critical: when breach_type is
    set, the trigger is left out. zone_category is the crossed geofence's
    category: entering a restricted zone is critical."""
    crossing = bool(str(breach_type or '').strip())
    if (crossing and str(zone_category or '').strip().lower() == 'restricted'
            and str(breach_type).strip().lower() != 'exit'):
        return 'critical'
    text = _text(event_name, condition, '' if crossing else trigger_value)
    for level, patterns in _COMPILED:
        if any(p.search(text) for p in patterns):
            return level
    if crossing:
        return 'warning'
    return DEFAULT
