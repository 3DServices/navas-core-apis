"""
test_engine_time.py — engine-on time at a stop, from ignition readings, with
no database.

engine_time imports only datetime, so it loads straight from its path.

Run:  python -m unittest tests/test_engine_time.py
"""

import importlib.util
import os
import unittest
from datetime import datetime, timedelta

_PATH = os.path.join(os.path.dirname(__file__), '..', 'endpoints',
                     'engine_time.py')
_spec = importlib.util.spec_from_file_location('engine_time', _PATH)
et = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(et)

T0 = datetime(2026, 10, 30, 15, 50)


def fix(minutes, ignition):
    return {'at': T0 + timedelta(minutes=minutes), 'ignition': ignition}


class EngineOn(unittest.TestCase):

    def test_on_counts_until_the_next_fix(self):
        fixes = [fix(0, 'ON'), fix(1, 'ON'), fix(2, 'OFF'), fix(30, 'OFF')]
        self.assertEqual(et.engine_on(fixes, T0, T0 + timedelta(hours=1)),
                         (120, 4))

    def test_a_long_silence_after_on_counts_only_up_to_the_cap(self):
        fixes = [fix(0, 'ON'), fix(60, 'OFF')]
        secs, _ = et.engine_on(fixes, T0, T0 + timedelta(hours=2))
        self.assertEqual(secs, 600)

    def test_the_last_on_reading_runs_to_the_span_end(self):
        fixes = [fix(0, 'OFF'), fix(10, 'ON')]
        secs, _ = et.engine_on(fixes, T0, T0 + timedelta(minutes=13))
        self.assertEqual(secs, 180)

    def test_nothing_counts_outside_the_span(self):
        fixes = [fix(0, 'ON'), fix(5, 'OFF')]
        secs, _ = et.engine_on(fixes, T0 + timedelta(minutes=2),
                               T0 + timedelta(hours=1))
        self.assertEqual(secs, 180)

    def test_no_readings_is_unknown_not_zero(self):
        self.assertEqual(et.engine_on([fix(0, None), fix(5, None)],
                                      T0, T0 + timedelta(hours=1)),
                         (None, 0))
        self.assertEqual(et.engine_on([], T0, T0 + timedelta(hours=1)),
                         (None, 0))

    def test_engine_off_throughout_is_zero(self):
        self.assertEqual(et.engine_on([fix(0, 'OFF'), fix(30, 'OFF')],
                                      T0, T0 + timedelta(hours=1)),
                         (0, 2))


class Spans(unittest.TestCase):

    def test_parses_both_time_forms(self):
        spans = et.parse_spans([
            {'from': '2026-10-30 00:00:00', 'to': '2026-10-30T12:19'},
        ])
        self.assertEqual(spans, [(datetime(2026, 10, 30),
                                  datetime(2026, 10, 30, 12, 19))])

    def test_refuses_what_it_cannot_read(self):
        for raw in (None, [], 'x', [{'from': 'soon', 'to': 'later'}],
                    [{'from': '2026-10-30 12:00', 'to': '2026-10-30 11:00'}],
                    [{'from': '2026-10-01 00:00', 'to': '2026-10-30 00:00'}],
                    [{'from': '2026-10-30 00:00', 'to': '2026-10-30 01:00'}]
                    * (et.MAX_SPANS + 1)):
            self.assertIsInstance(et.parse_spans(raw), str, raw)

    def test_fixes_in_a_span_come_oldest_first(self):
        fixes = [fix(9, 'ON'), fix(1, 'OFF'), fix(70, 'ON'),
                 {'at': None, 'ignition': 'ON'}]
        inside = et.in_span(fixes, T0, T0 + timedelta(hours=1))
        self.assertEqual([f['at'].minute - T0.minute for f in inside], [1, 9])


class Lookups(unittest.TestCase):

    def test_everything_is_looked_up_when_it_fits(self):
        self.assertEqual(et.share_lookups([10, 0, 5], budget=100), [10, 0, 5])

    def test_a_busy_day_shares_the_budget_and_no_span_is_left_out(self):
        shares = et.share_lookups([9000, 1000, 3], budget=1000)
        self.assertLessEqual(sum(shares), 1000)
        self.assertEqual(shares[2], 1)
        self.assertGreater(shares[0], shares[1])

    def test_sampling_spreads_evenly_and_keeps_the_first(self):
        picked = et.sample(list(range(100)), 10)
        self.assertEqual(picked, list(range(0, 100, 10)))
        self.assertEqual(et.sample([1, 2], 10), [1, 2])


if __name__ == '__main__':
    unittest.main()
