#!/usr/bin/env python3
"""
test_fleet_liveness.py -- the fb-009 fix.

fb-009 asked "How many vehicles are online?" four times. Three times Waswa
made one unit_status call, described a five-vehicle fleet from that one unit,
and called it "actively reporting" while stating its last report was eight
hours old. Once it made five calls and answered correctly.

The fix is not wording. It is that the whole fleet's heartbeat state is now
read in one call and put in front of the model, so answering from a sample is
not possible.

What these tests hold the fix to:

  * a failed read is NEVER counted as silence -- the mistake that once made a
    fleet audit report 272 units as never seen
  * "reporting" has a stated threshold, in the payload, not implied
  * a capped read says it was capped
  * the ambiguity note only fires when the person named a vehicle

No database: the Cassandra session and the unit register are stubbed.

Run:
    python tests/test_fleet_liveness.py
"""

import os
import sys
import types
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
if 'endpoints' not in sys.modules:
    pkg = types.ModuleType('endpoints')
    pkg.__path__ = [os.path.join(ROOT, 'endpoints')]
    sys.modules['endpoints'] = pkg

PASS, FAIL = [], []


def check(name, got, want):
    (PASS if got == want else FAIL).append(
        name if got == want else '%s\n      got  %r\n      want %r'
        % (name, got, want))


def truthy(name, got):
    check(name, bool(got), True)


class Row(object):
    def __init__(self, date_text, time_text):
        self.last_heartbeat_date = date_text
        self.last_heartbeat_time = time_text


class Future(object):
    def __init__(self, row=None, error=None):
        self._row, self._error = row, error

    def result(self):
        if self._error:
            raise self._error
        return self

    def one(self):
        return self._row


class Session(object):
    """Answers one heartbeat per imei. `plan` maps imei -> Row | 'error' | None."""

    def __init__(self, plan):
        self.plan = plan
        self.asked = []

    def prepare(self, cql):
        return cql

    def execute_async(self, stmt, params):
        imei = params[0]
        self.asked.append(imei)
        outcome = self.plan.get(imei, 'missing')
        if outcome == 'error':
            return Future(error=RuntimeError('read timed out'))
        if outcome == 'missing':
            return Future(row=None)
        return Future(row=outcome)


def run():
    import endpoints.waswa_fleet as wf

    now = datetime.now()
    recent = now - timedelta(minutes=6)        # 0.1h -> reporting
    stale = now - timedelta(hours=8, minutes=18)   # 8.3h -> silent, the fb-009 case

    def stamp(dt):
        return Row(dt.strftime('%d-%m-%Y'), dt.strftime('%H:%M:%S'))

    units = [{'imei': 'A1', 'name': 'UBJ 916W'},
             {'imei': 'B2', 'name': 'UBF 364U'},
             {'imei': 'C3', 'name': 'never seen'},
             {'imei': 'D4', 'name': 'unreadable'},
             {'imei': 'E5', 'name': 'bad stamp'}]

    session = Session({'A1': stamp(recent), 'B2': stamp(stale),
                       'C3': 'missing', 'D4': 'error',
                       'E5': Row('not-a-date', 'xx')})

    wf._units_of = lambda client: list(units)
    wf._cassandra = lambda: session
    wf._target_client = lambda scope, requested=None: 'CLIENT-1'

    out = wf.fleet_liveness(scope={'client_uid': 'CLIENT-1'})

    check('1a every unit was checked in one call',
          sorted(session.asked), ['A1', 'B2', 'C3', 'D4', 'E5'])
    check('1b the recent one is reporting',
          [u['name'] for u in out['reporting']], ['UBJ 916W'])
    check('1c the 8.3-hour one is silent, not reporting',
          [u['name'] for u in out['silent']], ['UBF 364U'])
    check('1d a unit with no heartbeat row is "never", not "silent"',
          [u['name'] for u in out['never_reported']], ['never seen'])
    check('1e A FAILED READ IS NOT SILENCE',
          sorted(u['name'] for u in out['could_not_read']),
          ['bad stamp', 'unreadable'])
    check('1f the counts add up to what was checked',
          sum(out['counts'].values()), out['units_checked'])
    check('1g the threshold is stated in the payload, not implied',
          out['live_within_hours'], wf.LIVE_WITHIN_HOURS)
    truthy('1h and the note warns against calling an unread unit offline',
           'do not describe it as offline' in out['note'].lower())
    check('1i the stale unit carries its age so the answer cannot round it away',
          out['silent'][0]['hours_since_last_report'] > 8, True)

    # ---- the fb-009 answer itself would now be contradicted by the data ----
    check('2a nothing is reporting except the one that is',
          out['counts']['reporting'], 1)
    check('2b and four units are accounted for in other states',
          out['counts']['silent'] + out['counts']['never_reported']
          + out['counts']['could_not_read'], 4)

    # ---- a capped fleet must say so ----
    many = [{'imei': 'U%d' % i, 'name': 'unit %d' % i}
            for i in range(wf.MAX_LIVENESS_UNITS + 10)]
    wf._units_of = lambda client: list(many)
    wf._cassandra = lambda: Session({u['imei']: 'missing' for u in many})
    capped = wf.fleet_liveness(scope={'client_uid': 'CLIENT-1'})
    check('3a a capped read checks only the cap',
          capped['units_checked'], wf.MAX_LIVENESS_UNITS)
    check('3b and reports the real fleet size', capped['units_registered'],
          len(many))
    truthy('3c and says it was capped', capped.get('truncated'))

    # ---- an unreachable register is not an empty fleet ----
    def explode(client):
        raise wf.FleetUnavailable('cassandra down')
    wf._units_of = explode
    try:
        wf.fleet_liveness(scope={'client_uid': 'CLIENT-1'})
        check('4a an unreachable register raises rather than returning empty',
              'returned', 'raised')
    except wf.FleetUnavailable:
        check('4a an unreachable register raises rather than returning empty',
              'raised', 'raised')

    # ---- the tool is offered to the model, and described correctly ----
    names = [t['function']['name'] for t in wf.TOOL_SPECS]
    truthy('5a fleet_liveness is in the tool list', 'fleet_liveness' in names)
    truthy('5b dispatch can route it', 'fleet_liveness' in wf._DISPATCH)
    desc = next(t['function']['description'] for t in wf.TOOL_SPECS
                if t['function']['name'] == 'fleet_liveness')
    truthy('5c its description forbids answering from a billing status',
           'subscription' in desc.lower() or 'billing' in desc.lower())


def main():
    try:
        run()
    except Exception as error:      # noqa: BLE001
        import traceback
        traceback.print_exc()
        FAIL.append('SUITE CRASHED: %s' % error)
    for name in PASS:
        print('  ok   %s' % name)
    for name in FAIL:
        print('  FAIL %s' % name)
    print('')
    print('  %d passed, %d failed' % (len(PASS), len(FAIL)))
    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(main())
