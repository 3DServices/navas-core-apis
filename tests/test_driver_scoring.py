"""
test_driver_scoring.py -- driver scorecards: 100 less each violation's points,
with no database.

driver_scoring imports nothing, so it loads straight from its path; the
loader in drivers.py is run against a cursor that hands back canned rows.

Run:  python -m unittest tests/test_driver_scoring.py
"""

import importlib.util
import os
import sys
import unittest
from datetime import date, datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_PATH = os.path.join(os.path.dirname(__file__), '..', 'endpoints', 'driver_scoring.py')
_spec = importlib.util.spec_from_file_location('driver_scoring_pure', _PATH)
ds = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ds)

DRIVER = {'driver_uid': 'd-1', 'full_name': 'Okello John', 'status': 'active'}


def rules(**points):
    """Effective rules with the given points per code (others default)."""
    own = [{'score_uid': f'r-{c}', 'violation_parameter': c, 'points_denomination': p}
           for c, p in points.items()]
    return ds.rules_by_code(ds.effective_rules(own))


def v(code, at='2026-11-10 09:00'):
    return {'code': code, 'label': ds.VIOLATIONS[code][0], 'at': at,
            'vehicle': 'UBA 123X', 'detail': ''}


class Rules(unittest.TestCase):

    def test_defaults_cover_every_violation(self):
        eff = ds.effective_rules([])
        self.assertEqual([r['violation_parameter'] for r in eff], list(ds.VIOLATIONS))
        self.assertTrue(all(r['is_default'] for r in eff))
        speed = eff[0]
        self.assertEqual((speed['points_denomination'], speed['measured']), (5, True))
        night = next(r for r in eff if r['violation_parameter'] == 'night_driving')
        self.assertFalse(night['measured'])

    def test_own_rule_replaces_only_its_default(self):
        eff = ds.effective_rules([{'score_uid': 'mine', 'score_name': 'Speeding',
                                   'violation_parameter': 'Overspeeding',
                                   'points_denomination': '10', 'max_deduction': 30}])
        speed, geo = eff[0], eff[1]
        self.assertEqual((speed['score_uid'], speed['points_denomination'],
                          speed['max_deduction'], speed['is_default']),
                         ('mine', 10, 30, False))
        self.assertTrue(geo['is_default'])

    def test_old_free_text_parameters(self):
        self.assertEqual(ds.violation_code('harsh braking'), 'harsh_braking')
        self.assertEqual(ds.violation_code('Overspeeding'), 'overspeeding')
        self.assertEqual(ds.violation_code('speed'), 'overspeeding')
        self.assertIsNone(ds.violation_code('singing'))

    def test_validation(self):
        clean, errors = ds.validate_rule({'violation_parameter': 'fuel_exception',
                                          'points_denomination': '8'})
        self.assertEqual(errors, {})
        self.assertEqual(clean, {'violation_parameter': 'fuel_exception',
                                 'points_denomination': 8, 'max_deduction': None,
                                 'score_name': 'Fuel exception'})
        self.assertIn('violation_parameter', ds.validate_rule(
            {'violation_parameter': 'x', 'points_denomination': 5})[1])
        for bad in ('101', '-1', '2.5', 'many'):
            self.assertIn('points_denomination', ds.validate_rule(
                {'violation_parameter': 'overspeeding', 'points_denomination': bad})[1], bad)
        self.assertIn('max_deduction', ds.validate_rule(
            {'violation_parameter': 'overspeeding', 'points_denomination': 10,
             'max_deduction': 5})[1])
        self.assertEqual(ds.validate_rule({'violation_parameter': 'overspeeding',
                                           'points_denomination': 0})[1], {})


class Scoring(unittest.TestCase):

    def test_clean_driving_is_100_a(self):
        card = ds.scorecard(DRIVER, [], rules(), drove=True)
        self.assertEqual((card['score'], card['grade'], card['grade_label']),
                         (100, 'A', 'Excellent'))

    def test_deducts_per_violation(self):
        card = ds.scorecard(DRIVER, [v('overspeeding')] * 3 + [v('fuel_exception')],
                            rules(), drove=True)
        self.assertEqual(card['deducted'], 3 * 5 + 5)
        self.assertEqual((card['score'], card['grade']), (80, 'B'))
        speed = next(b for b in card['breakdown'] if b['violation'] == 'overspeeding')
        self.assertEqual((speed['count'], speed['points_each'], speed['deducted']), (3, 5, 15))

    def test_cap_and_floor(self):
        capped = ds.scorecard(DRIVER, [v('overspeeding')] * 10,
                              ds.rules_by_code(ds.effective_rules([
                                  {'violation_parameter': 'overspeeding',
                                   'points_denomination': 5, 'max_deduction': 20}])),
                              drove=True)
        self.assertEqual(capped['score'], 80)
        floored = ds.scorecard(DRIVER, [v('unauthorised_driving')] * 6, rules(), drove=True)
        self.assertEqual((floored['score'], floored['grade']), (0, 'D'))

    def test_zero_points_and_unmeasured_deduct_nothing(self):
        card = ds.scorecard(DRIVER, [v('overspeeding'), v('night_driving')],
                            rules(overspeeding=0), drove=True)
        self.assertEqual((card['score'], card['violation_count']), (100, 2))

    def test_no_driving_is_not_scored(self):
        card = ds.scorecard(DRIVER, [], rules(), drove=False)
        self.assertEqual((card['score'], card['grade'], card['grade_label']),
                         (None, None, 'No driving'))

    def test_grade_bands(self):
        self.assertEqual([ds.grade(s)[0] for s in (100, 90, 89, 75, 74, 60, 59, 0)],
                         ['A', 'A', 'B', 'B', 'C', 'C', 'D', 'D'])

    def test_ranking_ties_and_unscored_last(self):
        def card(name, score, n):
            return {'full_name': name, 'score': score, 'violation_count': n}
        ranked = ds.rank([card('Zed', 90, 2), card('Amy', 95, 1), card('Bob', 90, 2),
                          card('Cat', None, 0), card('Dan', 90, 1)])
        self.assertEqual([(c['full_name'], c['rank']) for c in ranked],
                         [('Amy', 1), ('Dan', 2), ('Bob', 3), ('Zed', 3), ('Cat', None)])


class Attribution(unittest.TestCase):
    A = [{'driver_uid': 'd-1', 'device_imei': 'A', 'assigned_at': datetime(2026, 11, 1),
          'ended_at': datetime(2026, 11, 10)},
         {'driver_uid': 'd-2', 'device_imei': 'A', 'assigned_at': datetime(2026, 11, 10),
          'ended_at': None}]

    def test_driver_at(self):
        self.assertEqual(ds.driver_at(self.A, 'A', datetime(2026, 11, 5)), 'd-1')
        self.assertEqual(ds.driver_at(self.A, 'A', datetime(2026, 11, 10)), 'd-2')
        self.assertIsNone(ds.driver_at(self.A, 'A', datetime(2026, 10, 1)))
        self.assertIsNone(ds.driver_at(self.A, 'B', datetime(2026, 11, 5)))

    def test_which_alerts_are_violations(self):
        self.assertEqual(ds.alert_violation({'condition': 'speed_threshold'}), 'overspeeding')
        self.assertEqual(ds.alert_violation({'condition': 'geofence_breach'}), 'geofence_breach')
        self.assertEqual(ds.alert_violation({
            'condition': 'driver_unauthorised',
            'trigger_value': 'Unauthorised driver: X is assigned to Y but their permit expired'}),
            'unauthorised_driving')
        self.assertIsNone(ds.alert_violation({
            'condition': 'driver_unauthorised',
            'trigger_value': 'Unauthorised driver: an attempt to assign X to Y was refused (..)'}))
        self.assertIsNone(ds.alert_violation({'condition': 'ignition_change'}))

    def test_fuel(self):
        flagged = {'flags': [{'kind': 'discrepancy', 'code': 'not_stopped'}]}
        self.assertEqual(ds.fuel_violation(flagged), 'fuel_exception')
        self.assertIsNone(ds.fuel_violation({'flags': [{'kind': 'notice'}]}))
        self.assertIsNone(ds.fuel_violation(dict(flagged, voided=True)))


# ── the loader, against canned rows ──────────────────────────────────────────

class Cursor(object):
    def __init__(self, answers):
        self.answers, self.sql = list(answers), []

    def execute(self, sql, params=None):
        self.sql.append((sql, params))

    def fetchall(self):
        return self.answers.pop(0)

    def fetchone(self):
        return self.answers.pop(0)


class LoadScorecards(unittest.TestCase):

    def setUp(self):
        import endpoints.drivers as drivers
        self.drivers = drivers
        self._names = drivers._vehicle_names
        drivers._vehicle_names = lambda imeis: {i: f'Car {i}' for i in imeis}

    def tearDown(self):
        self.drivers._vehicle_names = self._names

    def test_scores_rank_and_attribute(self):
        cur = Cursor([
            {'n': 2},                                    # _rules_ready
            [{'score_uid': 'r1', 'score_name': 'Speeding', 'violation_parameter':
              'overspeeding', 'points_denomination': '10', 'max_deduction': None}],
            [{'driver_uid': 'd-1', 'full_name': 'Okello John', 'status': 'active'},
             {'driver_uid': 'd-2', 'full_name': 'Auma Grace', 'status': 'active'},
             {'driver_uid': 'd-3', 'full_name': 'Idle Ian', 'status': 'active'}],
            [{'driver_uid': 'd-1', 'device_imei': 'A', 'assigned_at': datetime(2026, 11, 1),
              'ended_at': None},
             {'driver_uid': 'd-2', 'device_imei': 'B', 'assigned_at': datetime(2026, 11, 1),
              'ended_at': None}],
            [  # alerts: one recorded driver, one by assignment, one not a violation
             {'date_triggered': datetime(2026, 11, 5, 9), 'device_imei': 'A',
              'device_name': 'UBA', 'condition': 'speed_threshold',
              'trigger_value': 'Speeding at 92', 'driver_uid': None},
             {'date_triggered': datetime(2026, 11, 6, 9), 'device_imei': 'B',
              'device_name': 'UBB', 'condition': 'speed_threshold',
              'trigger_value': 'Speeding at 99', 'driver_uid': 'd-1'},
             {'date_triggered': datetime(2026, 11, 6, 9), 'device_imei': 'B',
              'device_name': 'UBB', 'condition': 'driver_unauthorised',
              'trigger_value': 'an attempt to assign X to UBB was refused', 'driver_uid': 'd-2'}],
            [{'issue_uid': 'i1', 'device_imei': 'B', 'driver_uid': 'd-2',
              'issued_at': datetime(2026, 11, 7, 8), 'flags': 'not_stopped'}],
        ])
        cards, eff = self.drivers.load_scorecards(cur, 'c-1', date(2026, 11, 1),
                                                   date(2026, 11, 19))
        by = {c['full_name']: c for c in cards}
        self.assertEqual(by['Okello John']['score'], 80)        # 2 x 10 (own rule)
        self.assertEqual(by['Okello John']['violations'][0]['vehicle'], 'Car B')
        self.assertEqual(by['Auma Grace']['score'], 95)         # 1 fuel x 5 (default)
        self.assertIsNone(by['Idle Ian']['score'])
        self.assertEqual([c['full_name'] for c in cards],
                         ['Auma Grace', 'Okello John', 'Idle Ian'])
        self.assertEqual(eff[0]['points_denomination'], 10)
        # Every query after the readiness check is scoped to the client.
        self.assertTrue(all(p and p[0] == 'c-1' for _, p in cur.sql[1:]))

    def test_no_drivers(self):
        cur = Cursor([{'n': 0}, []])
        cards, eff = self.drivers.load_scorecards(cur, 'c-1', date(2026, 11, 1),
                                                   date(2026, 11, 19))
        self.assertEqual(cards, [])
        self.assertTrue(all(r['is_default'] for r in eff))


class ScorecardReport(unittest.TestCase):

    def test_rows(self):
        import endpoints.driver_report as dr
        card = ds.scorecard(DRIVER, [v('overspeeding')] * 2, rules(), drove=True)
        card['rank'] = 1
        row = dr.scorecard_rows([card])[dr.ALL_DRIVERS][0]
        self.assertEqual(row, {'rank': '1', 'driver': 'Okello John', 'score': '90',
                               'grade': 'A - Excellent', 'violations': '2',
                               'points_deducted': '10',
                               'breakdown': 'Overspeeding x2 (-10)', 'status': 'Active'})
        idle = ds.scorecard(DRIVER, [], rules(), drove=False)
        idle['rank'] = None
        row = dr.scorecard_rows([idle])[dr.ALL_DRIVERS][0]
        self.assertEqual((row['rank'], row['score'], row['grade']), ('', '', 'No driving'))
        self.assertEqual(dr.scorecard_rows([]), {})


if __name__ == '__main__':
    unittest.main()
