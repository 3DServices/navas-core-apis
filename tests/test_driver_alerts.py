"""
test_driver_alerts.py -- the client-wide driver rules (driver_permit_expiry,
driver_unauthorised) and the driver recorded on every alert, with no database.

alert_conditions decides (loaded from its path, as in test_alert_conditions);
alert_engine's driver sweep, blocked-assignment alerts and write_alert are run
with their reads and writes replaced by recorders.

Run:  python -m unittest tests/test_driver_alerts.py
"""

import importlib.util
import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import endpoints.alert_engine as engine                       # noqa: E402

_PATH = os.path.join(os.path.dirname(__file__), '..', 'endpoints', 'alert_conditions.py')
_spec = importlib.util.spec_from_file_location('alert_conditions_pure', _PATH)
ac = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ac)

TODAY = date(2026, 11, 19)


def driver(**over):
    base = {'driver_uid': 'd-1', 'client_uid': 'c-1', 'full_name': 'Okello John',
            'status': 'active', 'permit_expiry': date(2027, 6, 30),
            'current_imei': '', 'current_name': ''}
    base.update(over)
    return base


# ── parsing ──────────────────────────────────────────────────────────────────

class Parse(unittest.TestCase):

    def test_permit_days(self):
        self.assertEqual(ac.parse_config(ac.DRIVER_PERMIT, '30'), {'days': 30})
        self.assertEqual(ac.parse_config(ac.DRIVER_PERMIT, '0'), {'days': 0})
        self.assertEqual(ac.parse_config(ac.DRIVER_PERMIT, '{"value": "14"}'), {'days': 14})
        for bad in ('91', '-1', '7.5', 'soon', ''):
            self.assertIsNone(ac.parse_config(ac.DRIVER_PERMIT, bad), bad)

    def test_unauthorised_checks(self):
        both = {'checks': list(ac.UNAUTHORISED_CHECKS)}
        self.assertEqual(ac.parse_config(ac.DRIVER_UNAUTHORISED, 'all'), both)
        self.assertEqual(ac.parse_config(ac.DRIVER_UNAUTHORISED, ''), both)
        self.assertEqual(ac.parse_config(ac.DRIVER_UNAUTHORISED, '{"checks": "all"}'), both)
        self.assertEqual(ac.parse_config(ac.DRIVER_UNAUTHORISED, 'blocked_assignment'),
                         {'checks': ['blocked_assignment']})
        self.assertEqual(ac.parse_config(
            ac.DRIVER_UNAUTHORISED, '["blocked_assignment", "expired_while_assigned"]'),
            {'checks': ['expired_while_assigned', 'blocked_assignment']})
        self.assertIsNone(ac.parse_config(ac.DRIVER_UNAUTHORISED, 'speeding'))
        self.assertIsNone(ac.parse_config(ac.DRIVER_UNAUTHORISED, '[]'))

    def test_driver_rules_are_supported_and_client_wide(self):
        for c in (ac.DRIVER_PERMIT, ac.DRIVER_UNAUTHORISED):
            self.assertIn(c, ac.SUPPORTED)
            self.assertIn(c, ac.CLIENT_WIDE)
        self.assertNotIn(ac.SPEED, ac.CLIENT_WIDE)


# ── permit expiry ────────────────────────────────────────────────────────────

class Permit(unittest.TestCase):
    CFG = {'days': 14}

    def run_on(self, state, **over):
        return ac.evaluate_permit(self.CFG, state, driver(**over), TODAY)

    def test_far_off_is_quiet(self):
        self.assertEqual(self.run_on(None, permit_expiry=date(2026, 12, 31)), ([], {}))

    def test_warns_once_inside_the_window(self):
        alerts, state = self.run_on(None, permit_expiry=date(2026, 11, 29))
        self.assertEqual(len(alerts), 1)
        self.assertIn('expires in 10 days (29 Nov 2026)', alerts[0]['trigger_value'])
        self.assertEqual(state, {'expiry': '2026-11-29', 'sent': 'warned'})
        again, same = self.run_on(state, permit_expiry=date(2026, 11, 29))
        self.assertEqual((again, same), ([], state))

    def test_tomorrow_and_today(self):
        alerts, _ = self.run_on(None, permit_expiry=date(2026, 11, 20))
        self.assertIn('expires tomorrow', alerts[0]['trigger_value'])
        alerts, _ = self.run_on(None, permit_expiry=TODAY)
        self.assertIn('expires today', alerts[0]['trigger_value'])

    def test_then_once_more_when_it_expires(self):
        warned = {'expiry': '2026-11-18', 'sent': 'warned'}
        alerts, state = self.run_on(warned, permit_expiry=date(2026, 11, 18),
                                    current_name='UBA 123X')
        self.assertIn('expired on 18 Nov 2026. They are still assigned to UBA 123X.',
                      alerts[0]['trigger_value'])
        self.assertEqual(state['sent'], 'expired')
        self.assertEqual(self.run_on(state, permit_expiry=date(2026, 11, 18))[0], [])

    def test_first_seen_already_expired_says_expired_only(self):
        alerts, state = self.run_on(None, permit_expiry=date(2026, 10, 1))
        self.assertEqual(len(alerts), 1)
        self.assertIn('cannot be assigned a vehicle', alerts[0]['trigger_value'])
        self.assertEqual(state['sent'], 'expired')

    def test_renewed_permit_starts_again(self):
        old = {'expiry': '2026-11-18', 'sent': 'expired'}
        self.assertEqual(self.run_on(old, permit_expiry=date(2027, 11, 18)), ([], {}))
        alerts, state = self.run_on(old, permit_expiry=date(2026, 11, 25))
        self.assertEqual(len(alerts), 1)
        self.assertEqual(state, {'expiry': '2026-11-25', 'sent': 'warned'})

    def test_zero_days_only_on_expiry(self):
        cfg = {'days': 0}
        self.assertEqual(ac.evaluate_permit(cfg, None, driver(permit_expiry=date(2026, 11, 20)), TODAY),
                         ([], {}))
        alerts, _ = ac.evaluate_permit(cfg, None, driver(permit_expiry=TODAY), TODAY)
        self.assertEqual(len(alerts), 1)


# ── unauthorised ─────────────────────────────────────────────────────────────

class Unauthorised(unittest.TestCase):
    ALL = {'checks': list(ac.UNAUTHORISED_CHECKS)}

    def test_expired_and_still_assigned(self):
        d = driver(permit_expiry=date(2026, 11, 1), current_name='UBA 123X')
        alerts, state = ac.evaluate_expired_assignment(self.ALL, None, d, TODAY)
        self.assertEqual(alerts[0]['trigger_value'],
                         'Unauthorised driver: Okello John is assigned to UBA 123X but '
                         'their permit expired on 1 Nov 2026.')
        self.assertEqual(state, {'expiry': '2026-11-01', 'vehicle': 'UBA 123X'})
        self.assertEqual(ac.evaluate_expired_assignment(self.ALL, state, d, TODAY), ([], state))

    def test_moved_to_another_vehicle_alerts_again(self):
        prior = {'expiry': '2026-11-01', 'vehicle': 'UBA 123X'}
        d = driver(permit_expiry=date(2026, 11, 1), current_name='UBB 456Y')
        self.assertEqual(len(ac.evaluate_expired_assignment(self.ALL, prior, d, TODAY)[0]), 1)

    def test_valid_or_unassigned_is_quiet(self):
        self.assertEqual(ac.evaluate_expired_assignment(
            self.ALL, None, driver(current_name='UBA 123X'), TODAY), ([], {}))
        self.assertEqual(ac.evaluate_expired_assignment(
            self.ALL, None, driver(permit_expiry=date(2026, 1, 1)), TODAY), ([], {}))

    def test_check_switched_off(self):
        d = driver(permit_expiry=date(2026, 11, 1), current_name='UBA 123X')
        cfg = {'checks': ['blocked_assignment']}
        self.assertEqual(ac.evaluate_expired_assignment(cfg, None, d, TODAY), ([], {}))

    def test_blocked_assignment(self):
        alerts = ac.blocked_assignment_alerts(self.ALL, 'Okello John', 'UBA 123X',
                                              'This driver is suspended.')
        self.assertEqual(alerts[0]['trigger_value'],
                         'Unauthorised driver: an attempt to assign Okello John to '
                         'UBA 123X was refused (This driver is suspended).')
        self.assertEqual(ac.blocked_assignment_alerts(
            {'checks': ['expired_while_assigned']}, 'x', 'y', 'z'), [])


# ── the engine ───────────────────────────────────────────────────────────────

def rule(uid, condition, config, owner='owner-1'):
    return {'event_uid': uid, 'name': f'Rule {uid}', 'owner_uid': owner,
            'condition': condition, 'config': config, 'channels': ['in_app', 'sms']}


class RecordingCursor(object):
    """Hands back queued answers for fetchall/fetchone in order."""

    def __init__(self, answers=()):
        self.answers, self.sql = list(answers), []

    def execute(self, sql, params=None):
        self.sql.append((sql, params))

    def fetchall(self):
        return self.answers.pop(0) if self.answers else []

    def fetchone(self):
        rows = self.fetchall()
        return rows[0] if rows else None


class EngineCase(unittest.TestCase):
    PATCHED = ('client_root', 'load_drivers', '_vehicle_names', 'save_state', 'write_alert')

    def setUp(self):
        self.saved = {n: getattr(engine, n) for n in self.PATCHED}
        self.written, self.states = [], []
        self.drivers = []
        engine.client_root = lambda cur, uid: {'owner-1': 'c-1', 'owner-2': 'c-2'}.get(uid, uid)
        engine.load_drivers = lambda cur, clients: [d for d in self.drivers
                                                    if d['client_uid'] in clients]
        engine._vehicle_names = lambda imeis: {i: f'Car {i}' for i in imeis}
        engine.save_state = lambda cur, r, key, state, alerted: \
            self.states.append((r['event_uid'], key, state, alerted))
        engine.write_alert = lambda cur, r, unit, alert, driver=None: \
            self.written.append((r['condition'], unit, alert['trigger_value'], driver))

    def tearDown(self):
        for name, fn in self.saved.items():
            setattr(engine, name, fn)

    def summary(self):
        return {'alerts': 0, 'alerts_by_condition': {}}


class DriverSweep(EngineCase):

    def test_permit_rule_covers_only_its_clients_drivers(self):
        self.drivers = [
            dict(driver(), permit_expiry=date(2026, 11, 25), current_imei='A'),
            dict(driver(), driver_uid='d-2', client_uid='c-2', permit_expiry=date(2026, 11, 25)),
        ]
        s = self.summary()
        engine.driver_sweep(RecordingCursor([[]]), [rule('p', ac.DRIVER_PERMIT, {'days': 30})],
                            TODAY, True, s)
        self.assertEqual(s['alerts'], 1)
        condition, unit, text, who = self.written[0]
        self.assertEqual(condition, ac.DRIVER_PERMIT)
        self.assertEqual(unit, {'imei': 'A', 'name': 'Okello John', 'client': 'c-1'})
        self.assertEqual(who, {'driver_uid': 'd-1', 'full_name': 'Okello John'})
        self.assertEqual(self.states, [('p', 'driver:d-1',
                                        {'expiry': '2026-11-25', 'sent': 'warned'}, True)])

    def test_remembered_state_stops_a_repeat(self):
        self.drivers = [dict(driver(), permit_expiry=date(2026, 11, 25))]
        remembered = [{'event_uid': 'p', 'device_imei': 'driver:d-1',
                       'condition': ac.DRIVER_PERMIT,
                       'state': '{"expiry": "2026-11-25", "sent": "warned"}'}]
        s = self.summary()
        engine.driver_sweep(RecordingCursor([remembered]),
                            [rule('p', ac.DRIVER_PERMIT, {'days': 30})], TODAY, True, s)
        self.assertEqual((s['alerts'], self.written, self.states), (0, [], []))

    def test_inactive_drivers_get_no_permit_alerts(self):
        self.drivers = [dict(driver(), status='inactive', permit_expiry=date(2026, 11, 25))]
        s = self.summary()
        engine.driver_sweep(RecordingCursor([[]]),
                            [rule('p', ac.DRIVER_PERMIT, {'days': 30})], TODAY, True, s)
        self.assertEqual(s['alerts'], 0)

    def test_expired_and_assigned_names_the_vehicle(self):
        self.drivers = [dict(driver(), permit_expiry=date(2026, 11, 1), current_imei='A')]
        s = self.summary()
        engine.driver_sweep(RecordingCursor([[]]),
                            [rule('u', ac.DRIVER_UNAUTHORISED,
                                  {'checks': list(ac.UNAUTHORISED_CHECKS)})], TODAY, True, s)
        self.assertEqual(len(self.written), 1)
        self.assertIn('assigned to Car A', self.written[0][2])

    def test_dry_run_counts_but_writes_nothing(self):
        self.drivers = [dict(driver(), permit_expiry=date(2026, 11, 25))]
        s = self.summary()
        engine.driver_sweep(RecordingCursor([[]]),
                            [rule('p', ac.DRIVER_PERMIT, {'days': 30})], TODAY, False, s)
        self.assertEqual(s['alerts'], 1)
        self.assertEqual((self.written, self.states), ([], []))

    def test_no_driver_rules_reads_nothing(self):
        cur = RecordingCursor()
        engine.driver_sweep(cur, [rule('s', ac.SPEED, {'limit': 80.0})], TODAY, True,
                            self.summary())
        self.assertEqual(cur.sql, [])


class BlockedAssignment(EngineCase):

    @staticmethod
    def row(uid, value, owner='owner-1'):
        return {'event_local_uid': uid, 'event_display_name': uid, 'owner_org_uid': owner,
                'event_condition': ac.DRIVER_UNAUTHORISED, 'event_condition_value': value,
                'notification_alert_method': '["in_app"]'}

    def test_written_for_the_clients_watching_rules(self):
        cur = RecordingCursor([[self.row('u1', 'all'),
                                self.row('u2', 'expired_while_assigned'),
                                self.row('u3', 'all', owner='owner-2')]])
        n = engine.blocked_assignment_alerts(
            cur, 'c-1', {'driver_uid': 'd-1', 'full_name': 'Okello John'}, 'A',
            'This driver is blacklisted.')
        self.assertEqual(n, 1)
        condition, unit, text, who = self.written[0]
        self.assertEqual(unit['imei'], 'A')
        self.assertIn('to Car A was refused (This driver is blacklisted)', text)
        self.assertEqual(who['driver_uid'], 'd-1')

    def test_no_rules_writes_nothing(self):
        n = engine.blocked_assignment_alerts(
            RecordingCursor([[]]), 'c-1', {'driver_uid': 'd-1', 'full_name': 'x'}, 'A', 'r')
        self.assertEqual((n, self.written), (0, []))


class WriteAlertDriver(unittest.TestCase):
    RULE = rule('r1', 'speed_threshold', {'limit': 80.0})
    UNIT = {'imei': 'A', 'name': 'UBA 123X', 'client': 'c-1'}
    ALERT = {'trigger_value': 'Speeding at 92 km/h'}

    def setUp(self):
        self.saved = (engine._DRIVER_COLUMNS, engine.client_root)
        engine.client_root = lambda cur, uid: 'c-1'

    def tearDown(self):
        engine._DRIVER_COLUMNS, engine.client_root = self.saved

    def insert(self, cur):
        return next((sql, params) for sql, params in cur.sql if 'INSERT' in sql)

    def test_assigned_driver_recorded_once_migration_060_is_in(self):
        engine._DRIVER_COLUMNS = True
        cur = RecordingCursor([[{'driver_uid': 'd-1', 'full_name': 'Okello John'}]])
        engine.write_alert(cur, self.RULE, self.UNIT, self.ALERT)
        sql, params = self.insert(cur)
        self.assertIn('driver_uid, driver_name', sql)
        self.assertEqual(params[-2:], ['d-1', 'Okello John'])

    def test_given_driver_wins_over_the_assignment(self):
        engine._DRIVER_COLUMNS = True
        cur = RecordingCursor()
        engine.write_alert(cur, self.RULE, self.UNIT, self.ALERT,
                           driver={'driver_uid': 'd-9', 'full_name': 'Auma Grace'})
        sql, params = self.insert(cur)
        self.assertEqual(params[-2:], ['d-9', 'Auma Grace'])
        self.assertFalse(any('dll_driver_assignments' in s for s, _ in cur.sql))

    def test_no_driver_columns_before_the_migration(self):
        engine._DRIVER_COLUMNS = None
        cur = RecordingCursor([[{'n': 0}]])
        engine.write_alert(cur, self.RULE, self.UNIT, self.ALERT)
        sql, params = self.insert(cur)
        self.assertNotIn('driver_uid', sql)
        self.assertEqual(len(params), 11)
        self.assertIsNone(engine._DRIVER_COLUMNS)   # asked again next time


if __name__ == '__main__':
    unittest.main()
