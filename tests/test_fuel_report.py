"""
test_fuel_report.py -- the rows of the FuelMath reports, with no database.

fuel_report imports only datetime, so it loads straight from its path.

Run:  python -m unittest tests/test_fuel_report.py
"""

import importlib.util
import os
import unittest

_PATH = os.path.join(os.path.dirname(__file__), '..', 'endpoints', 'fuel_report.py')
_spec = importlib.util.spec_from_file_location('fuel_report', _PATH)
fr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fr)


def issue(**over):
    """The shape fuel_rules.public_issue() returns."""
    base = {
        'issue_uid': 'i-1', 'device_imei': 'A', 'driver_uid': 'd-1',
        'driver_name': 'Okello John', 'issued_at': '2026-10-28T09:05:00',
        'fuel_type': 'diesel', 'litres': 40.0, 'unit_price': 5150.0,
        'total_cost': 206000.0, 'full_tank': True, 'station_name': 'Shell Jinja Road',
        'receipt_number': 'R-1', 'payment_method': 'fuel_card',
        'km_since_full': 320.0, 'litres_since_full': 40.0, 'km_per_l': 8.0,
        'flags': [{'code': 'not_stopped', 'kind': 'discrepancy', 'message': 'x'},
                  {'code': 'no_profile', 'kind': 'notice', 'message': 'y'}],
        'review_state': 'open', 'review_note': None, 'voided': False,
    }
    base.update(over)
    return base


PROFILE = {'baseline_km_per_l': 10.0, 'tolerance_pct': 20}


class Formats(unittest.TestCase):

    def test_money_and_litres(self):
        self.assertEqual(fr.money(206000.0), '206,000')
        self.assertEqual(fr.money(999.6), '1,000')
        self.assertEqual(fr.money(None), '')
        self.assertEqual(fr.litres(40.0), '40')
        self.assertEqual(fr.litres(33.333), '33.33')
        self.assertEqual(fr.litres('n/a'), '')


class Issuance(unittest.TestCase):

    def test_row(self):
        self.assertEqual(fr.issuance_row(issue()), {
            'date_logged': '2026-10-28', 'time_logged': '09:05',
            'driver': 'Okello John', 'fuel_type': 'Diesel', 'litres': '40',
            'unit_price': '5,150', 'total_cost': '206,000',
            'payment_method': 'Fuel card', 'receipt_number': 'R-1',
            'station_name': 'Shell Jinja Road', 'full_tank': 'Yes',
            'review': 'Needs review',
        })

    def test_missing_pieces_do_not_throw(self):
        row = fr.issuance_row({'issued_at': None, 'driver_uid': 'd-9'})
        self.assertEqual((row['date_logged'], row['driver'], row['total_cost']),
                         ('', 'd-9', ''))


class Consumption(unittest.TestCase):

    def test_measured_full_tank_against_the_profile(self):
        row = fr.consumption_row(issue(), PROFILE)
        # 320 km at 10 km/L needs 32 L; 8 L more, at 5,150 a litre.
        self.assertEqual(row, {
            'date_logged': '2026-10-28', 'driver': 'Okello John',
            'km_since_full': '320.0', 'litres_since_full': '40',
            'km_per_l': '8.00', 'expected_km_per_l': '10', 'excess_litres': '8',
            'excess_cost': '41,200', 'cost_per_km': '644',
        })

    def test_no_profile_leaves_the_comparison_empty(self):
        row = fr.consumption_row(issue(), None)
        self.assertEqual((row['km_per_l'], row['expected_km_per_l'],
                          row['excess_litres']), ('8.00', '', ''))

    def test_economical_span_has_no_excess(self):
        row = fr.consumption_row(issue(litres_since_full=30.0), PROFILE)
        self.assertEqual((row['excess_litres'], row['excess_cost']), ('0', '0'))

    def test_only_measured_full_tanks(self):
        self.assertIsNone(fr.consumption_row(issue(full_tank=False), PROFILE))
        self.assertIsNone(fr.consumption_row(issue(km_since_full=None), PROFILE))
        self.assertIsNone(fr.consumption_row(issue(litres_since_full=0), PROFILE))


class Exceptions(unittest.TestCase):

    def test_discrepancies_only(self):
        row = fr.exception_row(issue(review_state='explained',
                                     review_note='Pump queue'))
        self.assertEqual((row['problems'], row['review'], row['review_note']),
                         ('Vehicle not stopped', 'Explained', 'Pump queue'))

    def test_several_problems(self):
        row = fr.exception_row(issue(flags=[
            {'code': 'over_capacity', 'kind': 'discrepancy'},
            {'code': 'possible_duplicate', 'kind': 'discrepancy'}]))
        self.assertEqual(row['problems'], 'More than the tank holds; Possible duplicate')

    def test_notices_are_not_exceptions(self):
        self.assertIsNone(fr.exception_row(issue(flags=[
            {'code': 'no_profile', 'kind': 'notice'}])))


class RowsFor(unittest.TestCase):

    def test_grouped_by_vehicle_newest_first_without_voided(self):
        issues = [
            issue(issue_uid='1', issued_at='2026-10-01T08:00:00'),
            issue(issue_uid='2', issued_at='2026-10-20T08:00:00'),
            issue(issue_uid='3', issued_at='2026-10-25T08:00:00', voided=True),
            issue(issue_uid='4', device_imei='B', issued_at='2026-10-05T08:00:00'),
        ]
        rows = fr.rows_for('issuance', issues)
        self.assertEqual(set(rows), {'A', 'B'})
        self.assertEqual([r['date_logged'] for r in rows['A']],
                         ['2026-10-20', '2026-10-01'])

    def test_vehicles_with_nothing_to_show_are_left_out(self):
        issues = [issue(flags=[]), issue(device_imei='B')]
        self.assertEqual(set(fr.rows_for('exceptions', issues)), {'B'})

    def test_consumption_uses_each_vehicles_profile(self):
        rows = fr.rows_for('consumption', [issue(), issue(device_imei='B')], {'A': PROFILE})
        self.assertEqual(rows['A'][0]['expected_km_per_l'], '10')
        self.assertEqual(rows['B'][0]['expected_km_per_l'], '')

    def test_unknown_kind(self):
        with self.assertRaises(ValueError):
            fr.rows_for('teleport', [issue()])

    def test_empty_messages_read_as_no_data(self):
        # The app treats a 400 saying "no ... found" as an empty report.
        for kind in fr.KINDS:
            text = fr.EMPTY_MESSAGES[kind].lower()
            self.assertIn('no ', text)
            self.assertIn('found', text)


if __name__ == '__main__':
    unittest.main()
