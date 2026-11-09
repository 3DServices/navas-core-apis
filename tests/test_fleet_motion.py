#!/usr/bin/env python3
"""
test_fleet_motion.py -- "how many vehicles are moving".

Asked that on 6 Nov 2026, Waswa said 4 while Live Monitoring showed 2. It had
no tool that knows what a vehicle is doing, so it counted what it could:
units that were reporting (fleet_liveness) or had a trip (fleet_activity).
A parked vehicle reports too.

What these tests hold the fix to:

  * fleet_status counts by the dashboard's rule (fleet_summary.classify), the
    one the app and Live Monitoring follow
  * a parked unit whose tracker sleeps stays parked; one last seen idling
    weeks ago is silent, not idling (MOROTO GENSET)
  * live positions that cannot be read are said to be unreadable, not zero
  * an answer that counts moving / parked vehicles without fleet_status is
    sent back, and a sentence about one unit is not

No database: the unit register and the readings are stubbed.

Run:
    python tests/test_fleet_motion.py
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


def run():
    import endpoints.waswa_fleet as wf
    import endpoints.fleet as fleet
    import endpoints.waswa_v2 as v2
    import endpoints.assistant as assistant

    now = datetime.now()

    def reading(imei, name, minutes_ago=None, **snapshot):
        seen = None if minutes_ago is None else now - timedelta(minutes=minutes_ago)
        return {'imei': imei, 'name': name, 'snapshot': snapshot or None,
                'seen': seen, 'unread': False, 'never': False}

    # The fleet on 6 Nov, as the live feed had it.
    readings = [
        reading('1', 'UAJ 373X(HQT-DCS)', 1, motion_state='Moving',
                speed_log='44', ignition_state='ON', data_latitude='0.33',
                data_longitude='32.6'),
        reading('2', 'UBK 415T', 0, motion_state='Parked', speed_log='0',
                ignition_state='OFF', data_latitude='0.35', data_longitude='32.65'),
        reading('3', 'UA 628BV', 1, motion_state='Parked', speed_log='0',
                ignition_state='OFF', data_latitude='0.3', data_longitude='32.5'),
        # Reporting, but parked: fleet_liveness counted these as "live".
        reading('4', 'UAJ 378X(Mpigi)', 9 * 60, motion_state='Parked',
                speed_log='0', ignition_state='OFF', device_state='Offline',
                data_latitude='0.2', data_longitude='32.3'),
        reading('5', 'UAR 860Y(HQT-DCS)', 2 * 24 * 60, motion_state='Parked',
                speed_log='0', ignition_state='OFF', data_latitude='0.3',
                data_longitude='32.6'),
        reading('6', 'MOROTO GENSET', 30 * 24 * 60, motion_state='Idiling',
                speed_log='0', ignition_state='ON', data_latitude='2.53',
                data_longitude='34.66'),
        dict(reading('7', 'UAJ 712X(Kabale)'), never=True),
        dict(reading('8', 'lookup failed'), unread=True),
    ]
    units = [{'imei': r['imei'], 'name': r['name']} for r in readings]
    wf._units_of = lambda client: list(units)
    wf._target_client = lambda scope, requested=None: 'CLIENT-1'
    fleet._readings = lambda us: (list(readings), [])

    out = wf.fleet_status(scope={'client_uid': 'CLIENT-1'})
    counts = out['counts']
    check('1a one vehicle is moving, not every one that reports',
          counts['moving'], 1)
    check('1b parked: the two reporting now and the two whose trackers sleep',
          counts['parked'], 4)
    check('1c MOROTO GENSET, last seen idling 30 days ago, is silent, not idling',
          (counts['idling'], counts['silent']), (0, 1))
    check('1d never reported and unread are kept apart',
          (counts['never_reported'], counts['unread']), (1, 1))
    check('1e the moving unit is named, with its speed',
          [(u['name'], u['speed_kph']) for u in out['units']['moving']],
          [('UAJ 373X(HQT-DCS)', 44.0)])
    check('1f a parked unit quiet over a day is flagged, still parked',
          [u['name'] for u in out['units']['parked'] if u.get('tracker_quiet')],
          ['UAR 860Y(HQT-DCS)'])
    check('1g reporting now (parked ones included) is not the number moving',
          (out['reporting_now'], counts['moving']), (5, 1))
    truthy('1h the rule is stated in the payload',
           'parked' in out['rule'] and 'NOT offline' in out['rule'])
    check('1i the counts cover every unit', sum(counts.values()), len(units))

    # ---- live positions unreadable: said so, never a count ----
    def down(us):
        raise fleet._LiveStoreDown('redis timed out')
    fleet._readings = down
    gone = wf.dispatch('fleet_status', {}, scope={'client_uid': 'CLIENT-1'})
    check('2a an unreachable live store is reported unavailable',
          (gone.get('found'), gone.get('unavailable')), (False, True))
    truthy('2b and the model is told not to give a count',
           'do not give a count' in gone['reason'].lower())
    fleet._readings = lambda us: (list(readings), [])

    # ---- the tool is offered to the model, with motion pointed at it ----
    specs = {s['function']['name']: s['function']['description']
             for s in wf.TOOL_SPECS}
    truthy('3a fleet_status is offered', 'fleet_status' in specs)
    truthy('3b fleet_liveness says reporting is not moving',
           'Reporting is NOT moving' in specs['fleet_liveness'])
    truthy('3c fleet_activity points at fleet_status for now',
           'fleet_status' in specs['fleet_activity'])
    truthy('3d and it can be dispatched', 'fleet_status' in wf._DISPATCH)

    # ---- the question is recognised, so the state is read up front ----
    for q in ('How many vehicles are moving?', 'which trucks are parked',
              'is anything idling right now'):
        truthy('4 motion question: %s' % q, assistant._MOTION_QUESTION.search(q))
    for q in ('what is my token balance', 'Who is driving UBK 415T?',
              'Why has tracking stopped'):
        check('4 not a fleet motion question: %s' % q,
              assistant._MOTION_QUESTION.search(q), None)

    # ---- the answer check ----
    plan = v2.plan_turn('How many vehicles are moving?', surface='console')
    nothing = {'chunks': [], 'attempts': [], 'exhausted': False,
               'rejected_for_scope': []}
    issues = v2.verify('4 vehicles are moving right now.', plan, nothing,
                       tool_refs=['fleet_liveness(all)'])
    truthy('5a "4 vehicles are moving" from fleet_liveness is sent back', issues)
    check('5b the same count from fleet_status passes',
          v2.verify('1 vehicle is moving right now.', plan, nothing,
                    tool_refs=['fleet_status(all, prefetched)']), [])
    truthy('5b2 a failed read is no source for a count',
           v2.verify('4 vehicles are moving right now.', plan, nothing,
                     tool_refs=['fleet_status(unavailable)']))
    truthy('5c "2 of your 35 units are parked" needs fleet_status too',
           v2.verify('2 of your 35 units are parked.', plan, nothing,
                     tool_refs=['fleet_activity(1)']))
    truthy('5d so does "Moving: 3"',
           v2.verify('Moving: 3', plan, nothing, tool_refs=[]))
    check('5e one unit\'s story is not a fleet count',
          v2.verify('Since 07:48 UBK 415T has been parked.', plan, nothing,
                    tool_refs=['unit_status(UBK 415T)']), [])


if __name__ == '__main__':
    run()
    for name in PASS:
        print('  ok   %s' % name)
    for name in FAIL:
        print('  FAIL %s' % name)
    print('\n%d passed, %d failed' % (len(PASS), len(FAIL)))
    sys.exit(1 if FAIL else 0)
