#!/usr/bin/env python3
"""
test_alerts_tool.py -- what Waswa's alerts_recent tool reports.

Asked "what was my most recent alert and is it acknowledged?" from the app's
Alerts screen, Waswa said it could not find anything: it had no tool for
alerts. summarise_alerts is the part that shapes the rows for the model;
it is compiled out of waswa_fleet.py with the real severity_of, so these need
no database and cannot drift from the Alerts screen's severity.
"""

import ast
import io
import os
import sys
from datetime import datetime

_ROOT = os.path.join(os.path.dirname(__file__), '..')
_SOURCE = os.path.join(_ROOT, 'endpoints', 'waswa_fleet.py')


def _load():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        'alert_severity', os.path.join(_ROOT, 'endpoints', 'alert_severity.py'))
    severity = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(severity)

    tree = ast.parse(io.open(_SOURCE, encoding='utf-8').read())
    body = [n for n in tree.body
            if isinstance(n, ast.FunctionDef) and n.name == 'summarise_alerts']
    assert body, 'waswa_fleet.py no longer defines summarise_alerts'
    ns = {'severity_of': severity.severity_of}
    exec(compile(ast.Module(body=body, type_ignores=[]), _SOURCE, 'exec'), ns)
    return ns['summarise_alerts']


summarise = _load()
SINCE = datetime(2026, 9, 14)


def _row(name='Geofence Breach Alert - Kabale', vehicle='UAJ 712X(Kabale)',
         zone='danger zones', breach='entry', read=False,
         when=datetime(2026, 6, 24, 20, 52), ack=None, note=None):
    return (name, vehicle, 'geozone', '', zone, breach, read, when, ack,
            'acct' if ack else None, note)


def test_the_alert_on_the_screen_comes_back_as_the_screen_shows_it():
    out = summarise([_row()], {}, SINCE)
    alert = out['alerts'][0]
    assert alert['alert'] == 'Geofence Breach Alert - Kabale'
    assert alert['vehicle'] == 'UAJ 712X(Kabale)'
    assert alert['severity'] == 'warning'          # the screen's "Warning"
    assert alert['when'] == '2026-06-24 20:52'
    assert alert['acknowledged'] is False and alert['read'] is False
    assert out['by_severity'] == {'critical': 0, 'warning': 1, 'info': 0}
    assert out['unread'] == 1 and out['unacknowledged'] == 1


def test_entering_a_restricted_zone_is_critical_as_on_the_screen():
    out = summarise([_row(zone='Quarry')], {'quarry': 'restricted'}, SINCE)
    assert out['alerts'][0]['severity'] == 'critical'


def test_acknowledgement_is_reported_with_its_note():
    out = summarise([_row(read=True, ack='2026-10-12T09:41:07.123',
                          note='Called the driver')], {}, SINCE)
    alert = out['alerts'][0]
    assert alert['acknowledged'] is True
    assert alert['acknowledged_at'] == '2026-10-12 09:41'
    assert alert['acknowledge_note'] == 'Called the driver'
    assert out['unacknowledged'] == 0 and out['unread'] == 0


def test_no_rows_is_an_empty_summary_not_an_error():
    out = summarise([], {}, SINCE)
    assert out['count'] == 0 and out['alerts'] == []
    assert out['since'] == '2026-09-14'


if __name__ == '__main__':
    sys.path.insert(0, _ROOT)
    passed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith('test_') and callable(fn):
            fn()
            passed += 1
            print('  ok  ' + name)
    print(f'{passed}/{passed} passed')
