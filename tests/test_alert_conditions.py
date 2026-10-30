"""
test_alert_conditions.py — what each event-rule condition decides, with no
database.

alert_conditions imports only json, so it loads straight from its path.

Run:  python -m unittest tests/test_alert_conditions.py
"""

import importlib.util
import os
import unittest
from datetime import datetime, timedelta

_PATH = os.path.join(os.path.dirname(__file__), '..', 'endpoints',
                     'alert_conditions.py')
_spec = importlib.util.spec_from_file_location('alert_conditions', _PATH)
ac = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ac)

T0 = datetime(2026, 10, 29, 9, 0)


def fix(minute, speed=0, ignition=None, lat=0.0, lon=0.0):
    return {'at': T0 + timedelta(minutes=minute), 'speed': speed,
            'ignition': ignition, 'lat': lat, 'lon': lon}


class ParseConfig(unittest.TestCase):

    def test_speed(self):
        self.assertEqual(ac.parse_config('speed_threshold', '80'), {'limit': 80.0})
        self.assertEqual(ac.parse_config('SPEED_THRESHOLD', ' 80 '), {'limit': 80.0})
        self.assertEqual(ac.parse_config('speed_threshold', '{"value": "60"}'),
                         {'limit': 60.0})

    def test_speed_that_cannot_work(self):
        for value in ('', 'fast', '0', '2', '900', None):
            self.assertIsNone(ac.parse_config('speed_threshold', value), value)

    def test_ignition_direction(self):
        self.assertEqual(ac.parse_config('ignition_change', 'on'), {'direction': 'on'})
        self.assertEqual(ac.parse_config('ignition_change', 'OFF'), {'direction': 'off'})
        # "on or off" is the app's hint; anything not one way is both.
        self.assertEqual(ac.parse_config('ignition_change', 'on or off'),
                         {'direction': 'both'})
        self.assertEqual(ac.parse_config('ignition_change', ''), {'direction': 'both'})

    def test_offline_minutes(self):
        self.assertEqual(ac.parse_config('device_offline', '30'), {'minutes': 30})
        self.assertEqual(ac.parse_config('device_offline', '45.4'), {'minutes': 45})
        self.assertIsNone(ac.parse_config('device_offline', '1'))
        self.assertIsNone(ac.parse_config('device_offline', 'soon'))

    def test_geofence(self):
        self.assertEqual(
            ac.parse_config('geofence_breach', '{"zones": ["z1"], "breach_type": "exit"}'),
            {'zones': ['z1'], 'breach_type': 'exit'})
        self.assertEqual(
            ac.parse_config('geofence_breach', '{"zones": ["z1"], "breach_type": "?"}'),
            {'zones': ['z1'], 'breach_type': 'both'})
        self.assertIsNone(ac.parse_config('geofence_breach', 'enter'))
        self.assertIsNone(ac.parse_config('geofence_breach', '{"zones": []}'))

    def test_unknown_and_unsupported(self):
        self.assertIsNone(ac.parse_config('teleport', '1'))
        self.assertIsNone(ac.parse_config('low_battery', '20'))
        self.assertIn('low_battery', ac.UNSUPPORTED)
        self.assertNotIn('low_battery', ac.SUPPORTED)


class Speed(unittest.TestCase):
    cfg = {'limit': 80.0}

    def test_one_alert_per_episode(self):
        alerts, state = ac.evaluate_speed(self.cfg, None, [
            fix(0, 60), fix(1, 85), fix(2, 95), fix(3, 90)])
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]['trigger_value'], 'Speeding at 85 km/h (limit 80 km/h)')
        self.assertEqual(alerts[0]['at'], T0 + timedelta(minutes=1))
        self.assertEqual(state, {'over': True})

    def test_still_over_next_sweep_is_not_news(self):
        alerts, state = ac.evaluate_speed(self.cfg, {'over': True}, [fix(5, 92)])
        self.assertEqual(alerts, [])
        self.assertEqual(state, {'over': True})

    def test_hovering_at_the_limit_does_not_repeat(self):
        # 79 is under the limit but not 5 under it: the episode goes on.
        alerts, _ = ac.evaluate_speed(self.cfg, None, [
            fix(0, 82), fix(1, 79), fix(2, 83), fix(3, 78), fix(4, 81)])
        self.assertEqual(len(alerts), 1)

    def test_a_new_episode_after_slowing_down(self):
        alerts, state = ac.evaluate_speed(self.cfg, None, [
            fix(0, 90), fix(1, 60), fix(2, 88)])
        self.assertEqual(len(alerts), 2)
        self.assertEqual(state, {'over': True})

    def test_bad_readings_are_ignored(self):
        alerts, state = ac.evaluate_speed(self.cfg, None, [
            fix(0, 400), fix(1, None), fix(2, 'n/a'), fix(3, -5)])
        self.assertEqual(alerts, [])
        self.assertEqual(state, {'over': False})

    def test_capped_per_sweep(self):
        fixes = []
        for i in range(10):
            fixes += [fix(2 * i, 100), fix(2 * i + 1, 40)]
        alerts, _ = ac.evaluate_speed(self.cfg, None, fixes)
        self.assertEqual(len(alerts), ac.MAX_ALERTS_PER_SWEEP)


class Ignition(unittest.TestCase):

    def test_first_reading_is_remembered_not_reported(self):
        alerts, state = ac.evaluate_ignition({'direction': 'both'}, None,
                                             [fix(0, ignition='ON')])
        self.assertEqual(alerts, [])
        self.assertEqual(state, {'ignition': 'ON'})

    def test_changes_in_both_directions(self):
        alerts, state = ac.evaluate_ignition({'direction': 'both'}, {'ignition': 'OFF'}, [
            fix(0, ignition='ON'), fix(1, ignition='ON'), fix(30, ignition='OFF')])
        self.assertEqual([a['trigger_value'] for a in alerts],
                         ['Ignition on at 09:00', 'Ignition off at 09:30'])
        self.assertEqual(state, {'ignition': 'OFF'})

    def test_only_the_rules_direction(self):
        alerts, _ = ac.evaluate_ignition({'direction': 'off'}, {'ignition': 'OFF'}, [
            fix(0, ignition='ON'), fix(9, ignition='OFF')])
        self.assertEqual([a['trigger_value'] for a in alerts], ['Ignition off at 09:09'])

    def test_unknown_readings_are_not_changes(self):
        alerts, state = ac.evaluate_ignition({'direction': 'both'}, {'ignition': 'ON'}, [
            fix(0), fix(1, ignition=None), fix(2, ignition='ON')])
        self.assertEqual(alerts, [])
        self.assertEqual(state, {'ignition': 'ON'})

    def test_nothing_known_keeps_the_old_answer(self):
        _, state = ac.evaluate_ignition({'direction': 'both'}, {'ignition': 'OFF'}, [fix(0)])
        self.assertEqual(state, {'ignition': 'OFF'})


class Offline(unittest.TestCase):
    cfg = {'minutes': 30}
    now = datetime(2026, 10, 29, 12, 0)

    def test_first_sighting_records_without_alert(self):
        # Dead for a month when the rule was attached: not news.
        alerts, state = ac.evaluate_offline(self.cfg, None,
                                            self.now - timedelta(days=30), self.now)
        self.assertEqual(alerts, [])
        self.assertEqual(state, {'offline': True})

    def test_goes_silent(self):
        alerts, state = ac.evaluate_offline(self.cfg, {'offline': False},
                                            self.now - timedelta(minutes=47), self.now)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]['trigger_value'],
                         'No report for 47 min (last at 29 Oct 11:13)')
        self.assertEqual(state, {'offline': True})

    def test_once_until_it_reports_again(self):
        alerts, _ = ac.evaluate_offline(self.cfg, {'offline': True},
                                        self.now - timedelta(hours=5), self.now)
        self.assertEqual(alerts, [])
        alerts, state = ac.evaluate_offline(self.cfg, {'offline': True},
                                            self.now - timedelta(minutes=2), self.now)
        self.assertEqual(alerts, [])
        self.assertEqual(state, {'offline': False})

    def test_reporting_unit_stays_quiet(self):
        alerts, state = ac.evaluate_offline(self.cfg, {'offline': False},
                                            self.now - timedelta(minutes=10), self.now)
        self.assertEqual((alerts, state), ([], {'offline': False}))

    def test_paused_unit_is_not_reported_but_tracked(self):
        alerts, state = ac.evaluate_offline(self.cfg, {'offline': False},
                                            self.now - timedelta(hours=2), self.now,
                                            paused=True)
        self.assertEqual((alerts, state), ([], {'offline': True}))

    def test_never_reported(self):
        alerts, state = ac.evaluate_offline(self.cfg, {'offline': False}, None, self.now)
        self.assertEqual((alerts, state), ([], {'offline': False}))

    def test_long_silences_read_well(self):
        alerts, _ = ac.evaluate_offline(self.cfg, {'offline': False},
                                        self.now - timedelta(hours=3, minutes=5), self.now)
        self.assertTrue(alerts[0]['trigger_value'].startswith('No report for 3 h 5 min'))
        alerts, _ = ac.evaluate_offline(self.cfg, {'offline': False},
                                        self.now - timedelta(days=3), self.now)
        self.assertTrue(alerts[0]['trigger_value'].startswith('No report for 3 days'))


class Geofence(unittest.TestCase):
    # Zone z1 is everything with lat > 0.
    @staticmethod
    def contains(zone_uid, lat, lon):
        return lat > 0 if zone_uid == 'z1' else None

    def test_first_answer_is_not_a_crossing(self):
        crossings, inside = ac.geofence_crossings(['z1'], {}, [fix(0, lat=1)], self.contains)
        self.assertEqual(crossings, [])
        self.assertEqual(inside, {'z1': True})

    def test_every_fix_is_tested(self):
        # In and out again between two sweeps is still two crossings.
        crossings, inside = ac.geofence_crossings(
            ['z1'], {'z1': False}, [fix(0, lat=-1), fix(1, lat=1), fix(2, lat=-1)],
            self.contains)
        self.assertEqual([c[1] for c in crossings], ['enter', 'exit'])
        self.assertEqual(inside, {'z1': False})

    def test_unknown_zone_is_skipped(self):
        crossings, inside = ac.geofence_crossings(['gone'], {}, [fix(0, lat=1)], self.contains)
        self.assertEqual((crossings, inside), ([], {}))

    def test_rule_filters_zone_and_direction(self):
        crossings = [('z1', 'enter', fix(1)), ('z1', 'exit', fix(2)), ('z2', 'enter', fix(3))]
        names = {'z1': 'Depot', 'z2': 'Yard'}
        exit_only = ac.geofence_alerts({'zones': ['z1'], 'breach_type': 'exit'}, crossings, names)
        self.assertEqual([(a['trigger_value'], a['geozone_name'], a['breach_type'])
                          for a in exit_only], [('exit:Depot', 'Depot', 'exit')])
        both = ac.geofence_alerts({'zones': ['z1', 'z2'], 'breach_type': 'both'},
                                  crossings, names)
        self.assertEqual(len(both), 3)


def issue(**over):
    """The shape fuel_rules.public_issue() returns."""
    base = {'issue_uid': 'i-1', 'device_imei': '354002396040196',
            'issued_at': '2026-10-28T09:00:00', 'litres': 40.0,
            'station_name': 'Shell Jinja Road', 'full_tank': True,
            'km_since_full': 320.0, 'litres_since_full': 40.0, 'voided': False,
            'flags': [
                {'code': 'not_stopped', 'kind': 'discrepancy',
                 'message': 'The tracker shows the vehicle was not stopped.'},
                {'code': 'no_profile', 'kind': 'notice', 'message': 'No profile.'},
            ]}
    base.update(over)
    return base


PROFILE = {'baseline_km_per_l': 10.0, 'tolerance_pct': 20}


class FuelConfig(unittest.TestCase):

    def test_flagged_all(self):
        for value in ('all', 'ALL', '', '{"flags": "all"}', '{"flags": null}'):
            self.assertEqual(ac.parse_config('fuel_issue_flagged', value),
                             {'flags': None}, value)

    def test_flagged_codes(self):
        want = {'flags': ['not_stopped', 'over_capacity']}
        self.assertEqual(ac.parse_config('fuel_issue_flagged',
                                         'over_capacity, not_stopped'), want)
        self.assertEqual(ac.parse_config('fuel_issue_flagged',
                                         '["not_stopped", "over_capacity"]'), want)
        self.assertEqual(ac.parse_config(
            'fuel_issue_flagged', '{"flags": ["over_capacity", "not_stopped"]}'), want)
        self.assertIsNone(ac.parse_config('fuel_issue_flagged', '[]'))
        self.assertIsNone(ac.parse_config('fuel_issue_flagged', 'drop table;'))

    def test_consumption(self):
        self.assertEqual(ac.parse_config('high_fuel_consumption', 'profile'),
                         {'pct': None})
        self.assertEqual(ac.parse_config('high_fuel_consumption', '25%'), {'pct': 25.0})
        self.assertIsNone(ac.parse_config('high_fuel_consumption', '2'))
        self.assertIsNone(ac.parse_config('high_fuel_consumption', 'lots'))

    def test_both_are_checked_on_recording_not_on_the_sweep(self):
        self.assertEqual(set(ac.ON_FUEL_ISSUE),
                         {'fuel_issue_flagged', 'high_fuel_consumption'})
        self.assertTrue(set(ac.ON_FUEL_ISSUE) <= set(ac.SUPPORTED))


class FuelFlagged(unittest.TestCase):

    def test_a_discrepancy_alerts_once_with_the_reason(self):
        alerts = ac.evaluate_fuel_flagged({'flags': None}, issue())
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]['trigger_value'],
                         'Fuel issue flagged: 40 L at Shell Jinja Road on 28 Oct 09:00. '
                         'The tracker shows the vehicle was not stopped.')
        self.assertEqual(alerts[0]['at'], datetime(2026, 10, 28, 9, 0))

    def test_notices_alone_send_nothing(self):
        only_notice = issue(flags=[{'code': 'no_profile', 'kind': 'notice',
                                    'message': 'x'}])
        self.assertEqual(ac.evaluate_fuel_flagged({'flags': None}, only_notice), [])
        self.assertEqual(ac.evaluate_fuel_flagged({'flags': None}, issue(flags=[])), [])

    def test_only_the_rules_flags(self):
        self.assertEqual(ac.evaluate_fuel_flagged({'flags': ['over_capacity']}, issue()), [])
        self.assertEqual(len(ac.evaluate_fuel_flagged({'flags': ['not_stopped']},
                                                      issue())), 1)

    def test_voided_sends_nothing(self):
        self.assertEqual(ac.evaluate_fuel_flagged({'flags': None}, issue(voided=True)), [])


class FuelConsumption(unittest.TestCase):

    def test_over_the_profile_tolerance(self):
        # 320 km at 10 km/L expects 32 L; 40 L is 25% more, over the 20%.
        alerts = ac.evaluate_fuel_consumption({'pct': None}, issue(), PROFILE)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]['trigger_value'],
                         'High fuel consumption: 8.0 km/L over 320 km, expected 10 km/L '
                         '(25% more fuel than expected, 8 L)')

    def test_within_the_rules_own_percentage(self):
        self.assertEqual(ac.evaluate_fuel_consumption({'pct': 30.0}, issue(), PROFILE), [])

    def test_needs_full_tank_profile_and_distance(self):
        cfg = {'pct': None}
        self.assertEqual(ac.evaluate_fuel_consumption(
            cfg, issue(full_tank=False), PROFILE), [])
        self.assertEqual(ac.evaluate_fuel_consumption(cfg, issue(), None), [])
        self.assertEqual(ac.evaluate_fuel_consumption(
            cfg, issue(km_since_full=80.0, litres_since_full=20.0), PROFILE), [])
        self.assertEqual(ac.evaluate_fuel_consumption(
            cfg, issue(km_since_full=None), PROFILE), [])
        self.assertEqual(ac.evaluate_fuel_consumption(
            cfg, issue(voided=True), PROFILE), [])

    def test_economical_driving_is_quiet(self):
        self.assertEqual(ac.evaluate_fuel_consumption(
            {'pct': None}, issue(litres_since_full=30.0), PROFILE), [])


if __name__ == '__main__':
    unittest.main()
