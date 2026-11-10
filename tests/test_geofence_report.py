# -*- coding: utf-8 -*-
"""Tests for endpoints/geofence_report.py -- the Geofence Entry and Geofence
Exit reports.

geofence_report.py is pure, so it imports directly.

Run:  python tests/test_geofence_report.py
"""

import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'endpoints'))

import geofence_report as gr                              # noqa: E402

RESULTS = []


def check(name, ok, detail=''):
    RESULTS.append((name, bool(ok), detail))


def eq(name, got, want):
    check(name, got == want, 'got %r, want %r' % (got, want))


# ── which crossings a request selects ─────────────────────────────────────
eq('entry selects the alert engine\'s "enter"',
   'enter' in gr.breach_values('entry'), True)
eq('exit selects "exit"', 'exit' in gr.breach_values('exit'), True)
eq('entry does not select exits', 'exit' in gr.breach_values('entry'), False)
eq('exit does not select entries', 'enter' in gr.breach_values('exit'), False)
eq('any case', gr.breach_values('ENTRY'), gr.breach_values('entry'))
eq('"enter" and "entrance" mean entry too',
   (gr.breach_values('enter'), gr.breach_values('entrance')),
   (gr.ENTRY_VALUES, gr.ENTRY_VALUES))
eq('no breach: both directions, as before the split', gr.breach_values(None),
   None)
eq('an unknown breach: both directions', gr.breach_values('sideways'), None)

# ── rows ──────────────────────────────────────────────────────────────────
r = gr.row(datetime(2026, 10, 26, 12, 51, 46), 'Mbale Depot', 'enter',
           'Depot watch')
eq('a row', r, {'date_logged': '2026-10-26', 'time_logged': '12:51:46',
                'geozone_name': 'Mbale Depot', 'event_triggered': 'Entry',
                'rule_name': 'Depot watch'})
eq('exit reads Exit',
   gr.row(datetime(2026, 10, 26, 13, 2), 'Mbale Depot', 'exit', '')
   ['event_triggered'], 'Exit')
eq('an older console spelling still reads right',
   gr.direction('Entrance'), 'Entry')
eq('a zone with no name says so',
   gr.row(datetime(2026, 10, 26), None, 'exit', None)['geozone_name'],
   'Unknown zone')

# ── nothing found ─────────────────────────────────────────────────────────
eq('no entries', gr.empty_message('entry'), 'No Geofence Entries Found')
eq('no exits', gr.empty_message('exit'), 'No Geofence Exits Found')
eq('neither asked', gr.empty_message(None), 'No Geozone Events Found')


if __name__ == '__main__':
    failed = [x for x in RESULTS if not x[1]]
    for name, ok, detail in RESULTS:
        print('%s  %s%s' % ('PASS' if ok else 'FAIL', name,
                            '' if ok else '  -- ' + detail))
    print('\n%d passed, %d failed' % (len(RESULTS) - len(failed), len(failed)))
    sys.exit(1 if failed else 0)
