# -*- coding: utf-8 -*-
"""Tests for endpoints/alert_severity.py

alert_severity.py is pure, so it imports directly -- no Flask, no database.

Run:  python tests/test_alert_severity.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'endpoints'))

from alert_severity import severity_of                    # noqa: E402

RESULTS = []


def eq(name, got, want):
    RESULTS.append((name, got == want, 'got %r, want %r' % (got, want)))


# ── critical ──────────────────────────────────────────────────────────────
eq('sos', severity_of('SOS button pressed'), 'critical')
eq('sos inside a word is not sos', severity_of('Sosiani depot report'), 'info')
eq('panic', severity_of('', 'panic_button'), 'critical')
eq('tamper', severity_of('Device tampered'), 'critical')
eq('power cut', severity_of('', 'power_cut'), 'critical')
eq('fuel theft beats fuel', severity_of('Fuel theft suspected'), 'critical')
eq('towing', severity_of('Vehicle towed'), 'critical')

# ── warning ───────────────────────────────────────────────────────────────
eq('overspeed', severity_of('Overspeed', 'speed_limit', '92 km/h'), 'warning')
eq('harsh braking', severity_of('', 'harsh_braking'), 'warning')
eq('geofence exit', severity_of('Depot watch', 'geofence_breach', 'exit:Depot', 'exit'),
   'warning')
eq('zone name cannot raise a crossing',
   severity_of('Yard watch', 'geofence_breach', 'entry:Tow yard', 'entry'), 'warning')
eq('crossing on an unrecognised rule', severity_of('Watch', 'custom', 'x', 'entry'),
   'warning')
eq('low fuel', severity_of('Low fuel'), 'warning')
eq('offline', severity_of('GPS offline'), 'warning')
eq('low balance', severity_of('Tokens running low', 'low_balance'), 'warning')
eq('top-up limit', severity_of('Top-up limit reached', 'low_balance'), 'warning')
eq('top-up failed', severity_of('Top-up failed', 'top_up'), 'warning')
eq('unknown rule', severity_of('Door opened', 'door'), 'warning')
eq('empty row', severity_of(), 'warning')

eq('entering a restricted zone',
   severity_of('Yard watch', 'geofence_breach', 'entry:Yard', 'entry', 'restricted'),
   'critical')
eq('leaving a restricted zone', severity_of('Yard watch', 'geofence_breach',
                                            'exit:Yard', 'exit', 'Restricted'), 'warning')
eq('restricted only matters for crossings',
   severity_of('Ignition on', 'ignition', '', '', 'restricted'), 'info')

# ── info ──────────────────────────────────────────────────────────────────
eq('ignition', severity_of('Ignition on', 'ignition'), 'info')
eq('top-up preview', severity_of('Auto top-up (preview)', 'top_up'), 'info')
eq('approve top-up', severity_of('Approve your top-up', 'top_up'), 'info')
eq('None values', severity_of(None, 'ignition', None, None), 'info')


if __name__ == '__main__':
    failed = [r for r in RESULTS if not r[1]]
    for name, ok, detail in RESULTS:
        print('%s  %s%s' % ('PASS' if ok else 'FAIL', name,
                            '' if ok else '  -- ' + detail))
    print('\n%d passed, %d failed' % (len(RESULTS) - len(failed), len(failed)))
    sys.exit(1 if failed else 0)
