"""
test_alert_engine.py — the sweep for one unit, with its reads and writes
replaced by recorders.

alert_conditions decides; this checks that alert_engine.sweep_unit feeds it the
right facts, remembers what it said, and writes nothing on a dry run.

Run:  python -m unittest tests/test_alert_engine.py
"""

import os
import sys
import unittest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import endpoints.alert_engine as engine                       # noqa: E402

NOW = datetime(2026, 10, 29, 12, 0)


def fix(minute, speed=0, lat=0.0, io_uid=None):
    at = NOW + timedelta(minutes=minute)
    return {'at': at, 'at_utc': at - timedelta(hours=3), 'speed': speed,
            'lat': lat, 'lon': 32.5, 'io_uid': io_uid, 'data_idx': str(minute)}


def rule(uid, condition, config):
    return {'event_uid': uid, 'name': f'Rule {uid}', 'owner_uid': 'owner',
            'condition': condition, 'config': config, 'channels': ['in_app']}


UNIT = {'imei': '354002396040196', 'name': 'UBK 415T', 'client': 'c', 'events': []}


class SweepUnit(unittest.TestCase):

    def setUp(self):
        self.written, self.states, self.presence, self.cursors = [], [], [], []
        self.fixes, self.cursor = [], None
        self.remembered, self.known_presence = {}, {}
        self.heartbeat, self.source = None, None
        self.saved = {}
        for name in ('new_fixes', 'load_states', 'save_state', 'write_alert',
                     'load_presence', 'save_presence', 'save_cursor',
                     'last_heartbeat', 'ignition_source', 'attach_ignition'):
            self.saved[name] = getattr(engine, name)
        engine.new_fixes = lambda cur, s, imei, now: (self.fixes, self.cursor)
        engine.load_states = lambda cur, imei: self.remembered
        engine.save_state = lambda cur, r, imei, state, alerted: \
            self.states.append((r['event_uid'], state, alerted))
        engine.write_alert = lambda cur, r, unit, alert: \
            self.written.append((r['condition'], alert['trigger_value']))
        engine.load_presence = lambda cur, imei: self.known_presence
        engine.save_presence = lambda cur, imei, z, inside, ref: \
            self.presence.append((z, inside))
        engine.save_cursor = lambda cur, imei, c: self.cursors.append(c)
        engine.last_heartbeat = lambda s, stmt, imei: self.heartbeat
        engine.ignition_source = lambda s, imei: self.source

        def attach(session, fixes, source):
            for f in fixes:
                f['ignition'] = {'a': 'ON', 'b': 'OFF'}.get(f.get('io_uid'))
        engine.attach_ignition = attach

    def tearDown(self):
        for name, fn in self.saved.items():
            setattr(engine, name, fn)

    def summary(self):
        return {'units_no_new_positions': 0, 'units_without_ignition_input': 0,
                'first_seen': 0, 'alerts': 0, 'alerts_by_condition': {}}

    def sweep(self, rules, zones=None, live=True, paused=()):
        s = self.summary()
        engine.sweep_unit(None, None, UNIT, rules, zones or {}, NOW, live, s,
                          None, set(paused))
        return s

    def test_speeding_is_written_remembered_and_the_cursor_moves(self):
        self.fixes = [fix(0, 60), fix(1, 92)]
        self.cursor = self.fixes[-1]['at_utc']
        s = self.sweep([rule('r1', 'speed_threshold', {'limit': 80.0})])
        self.assertEqual(self.written, [('speed_threshold', 'Speeding at 92 km/h (limit 80 km/h)')])
        self.assertEqual(self.states, [('r1', {'over': True}, True)])
        self.assertEqual(self.cursors, [self.cursor])
        self.assertEqual((s['alerts'], s['alerts_by_condition']),
                         (1, {'speed_threshold': 1}))

    def test_dry_run_writes_nothing(self):
        self.fixes = [fix(0, 120)]
        self.cursor = self.fixes[-1]['at_utc']
        s = self.sweep([rule('r1', 'speed_threshold', {'limit': 80.0})], live=False)
        self.assertEqual(s['alerts'], 1)
        self.assertEqual((self.written, self.states, self.cursors), ([], [], []))

    def test_unchanged_state_is_not_rewritten(self):
        self.remembered = {'r1': {'condition': 'speed_threshold', 'state': {'over': True}}}
        self.fixes = [fix(0, 95)]
        self.sweep([rule('r1', 'speed_threshold', {'limit': 80.0})])
        self.assertEqual((self.written, self.states), ([], []))

    def test_state_from_another_condition_is_ignored(self):
        # The rule was edited from ignition to speed: start again.
        self.remembered = {'r1': {'condition': 'ignition_change',
                                  'state': '{"ignition": "ON"}'}}
        self.fixes = [fix(0, 50)]
        self.sweep([rule('r1', 'speed_threshold', {'limit': 80.0})])
        self.assertEqual(self.states, [('r1', {'over': False}, False)])

    def test_no_new_positions_is_counted_and_checks_nothing(self):
        s = self.sweep([rule('r1', 'speed_threshold', {'limit': 80.0})])
        self.assertEqual(s['units_no_new_positions'], 1)
        self.assertEqual((self.written, self.states, self.cursors), ([], [], []))

    def test_ignition_from_the_configured_input(self):
        self.source = 'io-239'
        self.remembered = {'r2': {'condition': 'ignition_change',
                                  'state': {'ignition': 'OFF'}}}
        self.fixes = [fix(0, io_uid='a'), fix(5, io_uid='b')]
        self.sweep([rule('r2', 'ignition_change', {'direction': 'both'})])
        self.assertEqual([w[1] for w in self.written],
                         ['Ignition on at 12:00', 'Ignition off at 12:05'])

    def test_no_ignition_input_is_not_guessed_from_speed(self):
        self.fixes = [fix(0, speed=40), fix(1, speed=0)]
        s = self.sweep([rule('r2', 'ignition_change', {'direction': 'both'})])
        self.assertEqual(s['units_without_ignition_input'], 1)
        self.assertEqual(self.written, [])

    def test_offline_reads_the_heartbeat_even_without_positions(self):
        self.heartbeat = NOW - timedelta(hours=2)
        self.remembered = {'r3': {'condition': 'device_offline', 'state': {'offline': False}}}
        s = self.sweep([rule('r3', 'device_offline', {'minutes': 30})])
        self.assertEqual(self.written, [('device_offline',
                                         'No report for 2 h (last at 29 Oct 10:00)')])
        # Offline needs no positions, so none were asked for.
        self.assertEqual(s['units_no_new_positions'], 0)

    def test_paused_unit_is_not_reported_offline(self):
        self.heartbeat = NOW - timedelta(hours=2)
        self.remembered = {'r3': {'condition': 'device_offline', 'state': {'offline': False}}}
        self.sweep([rule('r3', 'device_offline', {'minutes': 30})], paused=[UNIT['imei']])
        self.assertEqual(self.written, [])
        self.assertEqual(self.states, [('r3', {'offline': True}, False)])

    def test_geofence_entry_across_the_new_fixes(self):
        zones = {'z1': {'name': 'Depot',
                        'ring': [[32.0, 0.1], [33.0, 0.1], [33.0, 1.0], [32.0, 1.0]]}}
        self.known_presence = {'z1': {'is_inside': False}}
        self.fixes = [fix(0, lat=-0.5), fix(1, lat=0.5)]
        self.cursor = self.fixes[-1]['at_utc']
        self.sweep([rule('g1', 'geofence_breach', {'zones': ['z1'], 'breach_type': 'both'})],
                   zones=zones)
        self.assertEqual(self.written, [('geofence_breach', 'enter:Depot')])
        self.assertEqual(self.presence, [('z1', True)])

    def test_geofence_first_sighting_records_only(self):
        zones = {'z1': {'name': 'Depot',
                        'ring': [[32.0, 0.1], [33.0, 0.1], [33.0, 1.0], [32.0, 1.0]]}}
        self.fixes = [fix(0, lat=0.5)]
        s = self.sweep([rule('g1', 'geofence_breach', {'zones': ['z1'], 'breach_type': 'both'})],
                       zones=zones)
        self.assertEqual(self.written, [])
        self.assertEqual(self.presence, [('z1', True)])
        self.assertEqual(s['first_seen'], 1)


class FakeCursor(object):
    """Answers the one rule query fuel_issue_alerts makes."""

    def __init__(self, rows):
        self.rows, self.sql = rows, []

    def execute(self, sql, params=None):
        self.sql.append((sql, params))

    def fetchall(self):
        return self.rows


class FuelIssueAlerts(unittest.TestCase):

    ISSUE = {'device_imei': UNIT['imei'], 'issued_at': '2026-10-28T09:00:00',
             'litres': 40.0, 'station_name': '', 'full_tank': True,
             'km_since_full': 320.0, 'litres_since_full': 40.0, 'voided': False,
             'flags': [{'code': 'over_capacity', 'kind': 'discrepancy',
                        'message': 'More litres than the tank holds.'}]}

    def setUp(self):
        import endpoints.devices as devices
        self.devices = devices
        self.saved = {n: getattr(engine, n) for n in ('unit_with_rules', 'write_alert')}
        self.saved_session = devices.get_cassandra_session
        self.written = []

        def write(cur, r, unit, alert):
            self.written.append((r['condition'], unit['name'], alert['trigger_value']))
        engine.write_alert = write
        devices.get_cassandra_session = lambda: object()

    def tearDown(self):
        for name, fn in self.saved.items():
            setattr(engine, name, fn)
        self.devices.get_cassandra_session = self.saved_session

    @staticmethod
    def row(uid, condition, value):
        return {'event_local_uid': uid, 'event_display_name': uid,
                'owner_org_uid': 'o', 'event_condition': condition,
                'event_condition_value': value, 'notification_alert_method': ''}

    def test_both_fuel_rules_on_the_vehicle(self):
        engine.unit_with_rules = lambda s, imei: dict(UNIT, events=['f1', 'f2'])
        cur = FakeCursor([self.row('f1', 'fuel_issue_flagged', 'all'),
                          self.row('f2', 'high_fuel_consumption', 'profile')])
        sent = engine.fuel_issue_alerts(
            cur, self.ISSUE, {'baseline_km_per_l': 10, 'tolerance_pct': 20})
        self.assertEqual(sent, 2)
        self.assertEqual([w[0] for w in self.written],
                         ['fuel_issue_flagged', 'high_fuel_consumption'])
        # Only the vehicle's own rules, and only fuel ones, are asked for.
        _, params = cur.sql[0]
        self.assertEqual(params[0], ['f1', 'f2'])
        self.assertEqual(set(params[1]), {'fuel_issue_flagged', 'high_fuel_consumption'})

    def test_vehicle_without_rules_asks_nothing(self):
        engine.unit_with_rules = lambda s, imei: dict(UNIT, events=[])
        cur = FakeCursor([])
        self.assertEqual(engine.fuel_issue_alerts(cur, self.ISSUE, None), 0)
        self.assertEqual(cur.sql, [])

    def test_a_rule_saved_with_an_unreadable_value_is_skipped(self):
        engine.unit_with_rules = lambda s, imei: dict(UNIT, events=['f1'])
        cur = FakeCursor([self.row('f1', 'high_fuel_consumption', 'lots')])
        self.assertEqual(engine.fuel_issue_alerts(cur, self.ISSUE, None), 0)


if __name__ == '__main__':
    unittest.main()
