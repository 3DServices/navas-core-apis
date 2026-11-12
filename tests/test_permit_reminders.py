"""
test_permit_reminders.py — send_reminders with its database replaced by a
recorder. driver_rules decides the stage (tests/test_driver_rules.py); this
checks the right drivers are alerted once, filed under the client, and that a
dry run writes nothing.

Run:  python -m unittest tests/test_permit_reminders.py
"""

import os
import sys
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import endpoints.permit_reminders as pr                       # noqa: E402

TODAY = date(2026, 11, 11)


class Cursor:
    """Answers the due-drivers query with [rows]; records every write."""

    def __init__(self, rows):
        self.rows = rows
        self.writes = []
        self._last = None

    def execute(self, sql, args=None):
        if sql.lstrip().upper().startswith('INSERT'):
            self.writes.append((sql, args))
        self._last = sql

    def fetchall(self):
        return self.rows


def driver(uid, days_left, sent_for=None, sent_stage=None, imei=None):
    return {'driver_uid': uid, 'client_uid': 'client-1', 'full_name': f'Driver {uid}',
            'permit_expiry': TODAY + timedelta(days=days_left),
            'current_imei': imei, 'sent_for': sent_for, 'sent_stage': sent_stage}


class SendReminders(unittest.TestCase):
    def setUp(self):
        self._root = pr.client_root
        pr.client_root = lambda cur, uid: f'root-of-{uid}'

    def tearDown(self):
        pr.client_root = self._root

    def test_sends_once_per_stage_and_remembers(self):
        already = TODAY + timedelta(days=12)
        cur = Cursor([
            driver('a', 12, sent_for=already, sent_stage=14),   # 14 sent: nothing
            driver('b', 6, imei='354002396040196'),             # 7-day due
            driver('c', -1, sent_for=TODAY - timedelta(days=1), sent_stage=1),
        ])
        summary = pr.send_reminders(cur, TODAY)
        self.assertEqual(summary, {'checked': 3, 'sent': 2,
                                   'by_stage': {'7': 1, 'expired': 1}})
        alerts = [a for s, a in cur.writes if 'dll_event_notifications' in s]
        kept = [a for s, a in cur.writes if 'dll_driver_permit_reminders' in s]
        self.assertEqual(len(alerts), 2)
        self.assertEqual([k[0] for k in kept], ['b', 'c'])
        self.assertEqual([k[2] for k in kept], [7, 0])

        b = alerts[0]
        self.assertEqual(b[1], 'driver_permit:b')
        self.assertEqual(b[2], 'Driver permit expiring')
        self.assertEqual(b[3], '354002396040196', 'their current vehicle')
        self.assertEqual(b[4], 'Driver b')
        self.assertEqual(b[5], 'permit_expiring')
        self.assertIn('expires in 6 days', b[6])
        self.assertEqual(b[8], 'root-of-client-1', 'filed under the client')
        self.assertEqual(alerts[1][2], 'Driver permit expired')
        self.assertEqual(alerts[1][3], '', 'no vehicle: no IMEI')

    def test_dry_run_writes_nothing(self):
        cur = Cursor([driver('b', 6)])
        summary = pr.send_reminders(cur, TODAY, live=False)
        self.assertEqual(summary['sent'], 1)
        self.assertEqual(cur.writes, [])


if __name__ == '__main__':
    unittest.main()
