"""
test_driver_report.py -- the rows of the driver reports, with no database.

driver_report imports only datetime, so it loads straight from its path.

Run:  python -m unittest tests/test_driver_report.py
"""

import importlib.util
import os
import unittest
from datetime import date, datetime

_PATH = os.path.join(os.path.dirname(__file__), '..', 'endpoints', 'driver_report.py')
_spec = importlib.util.spec_from_file_location('driver_report', _PATH)
dr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dr)

TODAY = date(2026, 11, 18)
NOW = datetime(2026, 11, 18, 10, 0)
NAMES = {'A': 'UBA 123X', 'B': 'UBB 456Y'}


def driver(**over):
    """A dll_drivers row joined with the current assignment, as the route
    selects it."""
    base = {
        'driver_uid': 'd-1', 'full_name': 'Okello John', 'phone': '256772000001',
        'permit_number': 'UG123456', 'permit_expiry': date(2027, 6, 30),
        'permit_classes': 'B,CM', 'ibutton_id': '01A2B3C4D5E6', 'national_id':
        'CM90012345ABCD', 'employee_number': 'E-17', 'photo_file': 'd-1.jpg',
        'emergency_name': 'Akello Mary', 'emergency_phone': '256772000002',
        'home_branch': 'Kampala', 'notes': None, 'status': 'active',
        'status_reason': None, 'created_at': datetime(2026, 3, 1, 9, 0),
        'current_imei': 'A', 'assigned_at': datetime(2026, 10, 1, 8, 30),
    }
    base.update(over)
    return base


class Formats(unittest.TestCase):

    def test_duration(self):
        self.assertEqual(dr.duration(datetime(2026, 1, 1, 8), datetime(2026, 1, 4, 12)), '3 d 4 h')
        self.assertEqual(dr.duration(datetime(2026, 1, 1, 8), datetime(2026, 1, 1, 13, 12)), '5 h 12 min')
        self.assertEqual(dr.duration(datetime(2026, 1, 1, 8), datetime(2026, 1, 1, 8, 40)), '40 min')
        self.assertEqual(dr.duration(datetime(2026, 1, 2), datetime(2026, 1, 1)), '')

    def test_permit_note(self):
        self.assertEqual(dr.permit_note(date(2026, 11, 30), TODAY), 'Expires in 12 days')
        self.assertEqual(dr.permit_note(date(2026, 11, 19), TODAY), 'Expires tomorrow')
        self.assertEqual(dr.permit_note(TODAY, TODAY), 'Expires today')
        self.assertEqual(dr.permit_note(date(2026, 11, 17), TODAY), 'Expired 1 day ago')
        self.assertEqual(dr.permit_note(date(2026, 11, 15), TODAY), 'Expired 3 days ago')

    def test_permit_state_matches_driver_rules(self):
        self.assertEqual(dr.permit_state(date(2026, 12, 18), TODAY), 'expiring')
        self.assertEqual(dr.permit_state(date(2026, 12, 19), TODAY), 'valid')
        self.assertEqual(dr.permit_state(date(2026, 11, 17), TODAY), 'expired')
        self.assertEqual(dr.permit_state(None, TODAY), 'expired')


class Registry(unittest.TestCase):

    def test_row(self):
        rows = dr.registry_rows([driver()], TODAY, NAMES)
        row = rows[dr.ALL_DRIVERS][0]
        self.assertEqual(row['driver'], 'Okello John')
        self.assertEqual(row['permit_classes'], 'B, CM')
        self.assertEqual(row['permit_expiry'], '2027-06-30')
        self.assertEqual(row['permit_status'], 'Valid')
        self.assertEqual(row['current_vehicle'], 'UBA 123X')
        self.assertEqual(row['assigned_since'], '2026-10-01')
        self.assertEqual(row['status'], 'Active')
        self.assertEqual(row['emergency_contact'], 'Akello Mary · 256772000002')
        self.assertEqual(row['registered_on'], '2026-03-01')

    def test_sorted_by_name_and_unassigned(self):
        rows = dr.registry_rows([driver(full_name='Zziwa Paul', current_imei=None,
                                        assigned_at=None),
                                 driver(driver_uid='d-2', full_name='Auma Grace')],
                                TODAY, NAMES)[dr.ALL_DRIVERS]
        self.assertEqual([r['driver'] for r in rows], ['Auma Grace', 'Zziwa Paul'])
        self.assertEqual(rows[1]['current_vehicle'], '')

    def test_empty(self):
        self.assertEqual(dr.registry_rows([], TODAY), {})

    def test_unknown_vehicle_shows_imei(self):
        row = dr.registry_rows([driver(current_imei='Z')], TODAY, NAMES)[dr.ALL_DRIVERS][0]
        self.assertEqual(row['current_vehicle'], 'Z')


class Assignments(unittest.TestCase):

    def test_rows_per_driver_newest_first(self):
        held = [
            {'driver_uid': 'd-1', 'device_imei': 'B', 'assigned_at': datetime(2026, 9, 1, 8),
             'ended_at': datetime(2026, 9, 30, 17), 'end_reason': 'reassigned'},
            {'driver_uid': 'd-1', 'device_imei': 'A', 'assigned_at': datetime(2026, 10, 1, 8, 30),
             'ended_at': None, 'end_reason': None},
        ]
        rows = dr.assignment_rows([driver()], held, NOW, NAMES)['Okello John']
        self.assertEqual(rows[0]['vehicle'], 'UBA 123X')
        self.assertEqual(rows[0]['release_reason'], 'Still assigned')
        self.assertEqual(rows[0]['released_on'], '')
        self.assertEqual(rows[0]['duration'], '48 d 1 h')
        self.assertEqual(rows[1]['vehicle'], 'UBB 456Y')
        self.assertEqual(rows[1]['assigned_time'], '08:00')
        self.assertEqual(rows[1]['released_on'], '2026-09-30')
        self.assertEqual(rows[1]['release_reason'], 'Moved to another vehicle')
        self.assertEqual(rows[1]['duration'], '29 d 9 h')

    def test_drivers_without_assignments_left_out(self):
        self.assertEqual(dr.assignment_rows([driver()], [], NOW, NAMES), {})

    def test_same_name_drivers_get_distinct_sections(self):
        a = {'driver_uid': 'd-1', 'device_imei': 'A', 'assigned_at': NOW,
             'ended_at': None, 'end_reason': None}
        b = dict(a, driver_uid='d-2', device_imei='B')
        out = dr.assignment_rows([driver(), driver(driver_uid='d-2', employee_number='E-99')],
                                 [a, b], NOW, NAMES)
        self.assertEqual(list(out), ['Okello John', 'Okello John (E-99)'])

    def test_end_reasons_labelled(self):
        for code, label in dr.END_REASON_LABELS.items():
            row = dr.assignment_row({'device_imei': 'A', 'assigned_at': datetime(2026, 1, 1),
                                     'ended_at': datetime(2026, 1, 2), 'end_reason': code},
                                    NOW, NAMES)
            self.assertEqual(row['release_reason'], label)


class Compliance(unittest.TestCase):

    def test_compliant(self):
        self.assertEqual(dr.compliance(driver(), TODAY), (dr.COMPLIANT, []))

    def test_expired_permit_is_non_compliant(self):
        verdict, problems = dr.compliance(driver(permit_expiry=date(2026, 11, 1)), TODAY)
        self.assertEqual(verdict, dr.NON_COMPLIANT)
        self.assertIn('Permit expired', problems)

    def test_expiring_needs_attention(self):
        verdict, problems = dr.compliance(driver(permit_expiry=date(2026, 11, 30)), TODAY)
        self.assertEqual(verdict, dr.NEEDS_ATTENTION)
        self.assertEqual(problems, ['Permit expires in 12 days'])

    def test_suspended_but_assigned_is_non_compliant(self):
        verdict, problems = dr.compliance(driver(status='suspended'), TODAY)
        self.assertEqual(verdict, dr.NON_COMPLIANT)
        self.assertEqual(problems, ['Suspended but still assigned to a vehicle'])

    def test_blacklisted_unassigned_needs_attention(self):
        verdict, _ = dr.compliance(driver(status='blacklisted', current_imei=None), TODAY)
        self.assertEqual(verdict, dr.NEEDS_ATTENTION)

    def test_missing_details(self):
        verdict, problems = dr.compliance(
            driver(national_id=None, ibutton_id='', emergency_phone=None, photo_file=None), TODAY)
        self.assertEqual(verdict, dr.NEEDS_ATTENTION)
        self.assertEqual(problems, ['Missing: National ID, iButton tag, Emergency contact, Photo'])

    def test_inactive_is_its_own_section(self):
        verdict, problems = dr.compliance(
            driver(status='inactive', current_imei=None, permit_expiry=date(2025, 1, 1)), TODAY)
        self.assertEqual(verdict, dr.INACTIVE)
        self.assertIn('Permit expired', problems)

    def test_sections_worst_first(self):
        out = dr.compliance_rows([
            driver(driver_uid='ok', full_name='Okay'),
            driver(driver_uid='bad', full_name='Bad', permit_expiry=date(2026, 1, 1)),
            driver(driver_uid='soon', full_name='Soon', permit_expiry=date(2026, 12, 1)),
        ], TODAY, NAMES)
        self.assertEqual(list(out), [dr.NON_COMPLIANT, dr.NEEDS_ATTENTION, dr.COMPLIANT])
        self.assertEqual(out[dr.NON_COMPLIANT][0]['issues'], 'Permit expired')
        self.assertEqual(out[dr.COMPLIANT][0]['issues'], 'None')
        self.assertEqual(out[dr.NEEDS_ATTENTION][0]['permit_note'], 'Expires in 13 days')


class Fuel(unittest.TestCase):

    FLAGS = {'not_stopped': 'Vehicle not stopped'}
    REVIEW = {'open': 'Needs review', 'none': 'OK'}
    PAY = {'fuel_card': 'Fuel card'}

    def issue(self, **over):
        base = {
            'issue_uid': 'i-1', 'device_imei': 'A', 'driver_uid': 'd-1',
            'issued_at': '2026-10-28T09:05:00', 'fuel_type': 'diesel', 'litres': 40.0,
            'unit_price': 5150.0, 'total_cost': 206000.0, 'payment_method': 'fuel_card',
            'receipt_number': 'R-1', 'station_name': 'Shell Jinja Road',
            'flags': [{'code': 'not_stopped', 'kind': 'discrepancy', 'message': 'x'},
                      {'code': 'no_profile', 'kind': 'notice', 'message': 'y'}],
            'review_state': 'open', 'voided': False,
        }
        base.update(over)
        return base

    def test_row(self):
        out = dr.fuel_rows([driver()], [self.issue()], NAMES, self.FLAGS, self.REVIEW, self.PAY)
        row = out['Okello John'][0]
        self.assertEqual(row['date_logged'], '2026-10-28')
        self.assertEqual(row['time_logged'], '09:05')
        self.assertEqual(row['vehicle'], 'UBA 123X')
        self.assertEqual(row['fuel_type'], 'Diesel')
        self.assertEqual(row['litres'], '40')
        self.assertEqual(row['unit_price'], '5,150')
        self.assertEqual(row['total_cost'], '206,000')
        self.assertEqual(row['payment_method'], 'Fuel card')
        self.assertEqual(row['flagged'], 'Vehicle not stopped')   # notices left out
        self.assertEqual(row['review'], 'Needs review')

    def test_unflagged_and_voided(self):
        out = dr.fuel_rows([driver()], [self.issue(flags=[]),
                                        self.issue(issue_uid='i-2', voided=True)],
                           NAMES, self.FLAGS, self.REVIEW, self.PAY)
        rows = out['Okello John']
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['flagged'], 'No')

    def test_newest_first_and_driver_without_fuel_left_out(self):
        out = dr.fuel_rows([driver(), driver(driver_uid='d-2', full_name='Auma Grace')],
                           [self.issue(issued_at='2026-10-01T08:00:00'),
                            self.issue(issue_uid='i-2', issued_at='2026-10-20T08:00:00')],
                           NAMES, self.FLAGS, self.REVIEW, self.PAY)
        self.assertEqual(list(out), ['Okello John'])
        self.assertEqual([r['date_logged'] for r in out['Okello John']],
                         ['2026-10-20', '2026-10-01'])


if __name__ == '__main__':
    unittest.main()
