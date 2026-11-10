"""
test_io_events_store.py — the IO-event reader's logic, without a database.

Every test here corresponds to something the audits measured on the live
stores, not to something imagined:

  * data_idx is text in Cassandra and the table has no clustering column, so
    ordering must happen here and must be numeric. Real values from unit
    862846042622426 sort differently as text than as numbers.
  * the test unit's vendor is 'xirgo_global', which the route's two-branch
    vendor logic never handled.
  * dll_io_events_config holds zero rows, so every name lookup misses.
  * a failed lookup must raise rather than return an empty list.

io_events_store imports nothing at module level, so it loads from its path
without Flask or the Cassandra driver.
"""

import importlib.util
import os
import unittest

_PATH = os.path.join(os.path.dirname(__file__), '..', 'endpoints',
                     'io_events_store.py')
_spec = importlib.util.spec_from_file_location('io_events_store', _PATH)
ies = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ies)


class Row(object):
    def __init__(self, parent, event_uid, value, data_idx):
        self.io_parent_io_event_uid = parent
        self.event_uid_executed = event_uid
        self.event_value_executed = value
        self.data_idx = data_idx


class FakeSession(object):
    """Stands in for a Cassandra session, including concurrent execution."""

    def __init__(self, rows_by_uid=None, fail_uids=(), fail_prepare=False):
        self.rows_by_uid = rows_by_uid or {}
        self.fail_uids = set(fail_uids)
        self.fail_prepare = fail_prepare
        self.asked = []

    def prepare(self, cql):
        if self.fail_prepare:
            raise RuntimeError('prepare refused')
        self.cql = cql
        return 'STATEMENT'


def fake_concurrent(session, statement, args, concurrency=None,
                    raise_on_first_error=False):
    """Mirrors execute_concurrent_with_args: one (ok, result) per argument,
    in the order given."""
    out = []
    for (uid,) in args:
        session.asked.append(uid)
        if uid in session.fail_uids:
            out.append((False, RuntimeError('read timeout')))
        else:
            out.append((True, list(session.rows_by_uid.get(uid, []))))
    return out


class _Patched(object):
    """Installs the fake execute_concurrent_with_args for the duration."""

    def __enter__(self):
        import sys
        import types
        self.created = 'cassandra.concurrent' not in sys.modules
        if self.created:
            pkg = sys.modules.setdefault('cassandra',
                                         types.ModuleType('cassandra'))
            mod = types.ModuleType('cassandra.concurrent')
            sys.modules['cassandra.concurrent'] = mod
            pkg.concurrent = mod
        self.mod = sys.modules['cassandra.concurrent']
        self.previous = getattr(self.mod, 'execute_concurrent_with_args', None)
        self.mod.execute_concurrent_with_args = fake_concurrent
        return self

    def __exit__(self, *exc):
        if self.previous is not None:
            self.mod.execute_concurrent_with_args = self.previous
        return False


class Ordering(unittest.TestCase):

    def test_data_idx_orders_as_a_number_not_as_text(self):
        """The real values from 862846042622426 on 25-09-2026. Sorted as text
        the largest, 2015440768, lands fifth."""
        real = ['968159659', '1166630054', '769668690', '561863297',
                '1264025644', '1977860551', '809268972', '2015440768']
        rows = [Row('u1', 'in5', 'v', idx) for idx in real]
        with _Patched():
            got = ies.events_for(FakeSession({'u1': rows}), ['u1'])
        order = [e['data_idx'] for e in got['u1']]
        self.assertEqual(order[0], '2015440768')
        self.assertEqual(order, sorted(real, key=int, reverse=True))
        self.assertNotEqual(order, sorted(real, reverse=True),
                            'text order and numeric order must differ here, '
                            'or this test proves nothing')

    def test_non_numeric_data_idx_sorts_last_without_raising(self):
        rows = [Row('u1', 'a', 'v', 'NoData'), Row('u1', 'b', 'v', '42'),
                Row('u1', 'c', 'v', None)]
        with _Patched():
            got = ies.events_for(FakeSession({'u1': rows}), ['u1'])
        self.assertEqual(got['u1'][0]['data_idx'], '42')
        self.assertEqual(len(got['u1']), 3)


class Reading(unittest.TestCase):

    def test_one_entry_per_uid_including_the_empty_ones(self):
        rows = {'u1': [Row('u1', 'in5', '1', '7')]}
        with _Patched():
            got = ies.events_for(FakeSession(rows), ['u1', 'u2'])
        self.assertEqual(sorted(got), ['u1', 'u2'])
        self.assertEqual(len(got['u1']), 1)
        self.assertEqual(got['u2'], [],
                         'looked and found none must be distinguishable from '
                         'never looked, which is absence from the dict')

    def test_duplicate_and_blank_uids_are_asked_once(self):
        session = FakeSession({'u1': []})
        with _Patched():
            ies.events_for(session, ['u1', 'u1', '', None, '  ', 'u1'])
        self.assertEqual(session.asked, ['u1'])

    def test_no_uids_asks_nothing(self):
        session = FakeSession()
        with _Patched():
            self.assertEqual(ies.events_for(session, []), {})
        self.assertEqual(session.asked, [])

    def test_fields_carried_through(self):
        rows = {'u1': [Row('u1', 'in5', '1', '7')]}
        with _Patched():
            got = ies.events_for(FakeSession(rows), ['u1'])
        self.assertEqual(got['u1'][0], {'event_uid': 'in5', 'value': '1',
                                        'data_idx': '7'})


class Unavailable(unittest.TestCase):

    def test_no_session_raises(self):
        with self.assertRaises(ies.IoEventsUnavailable):
            ies.events_for(None, ['u1'])

    def test_prepare_failure_raises(self):
        with _Patched():
            with self.assertRaises(ies.IoEventsUnavailable):
                ies.events_for(FakeSession(fail_prepare=True), ['u1'])

    def test_one_failed_lookup_raises_rather_than_returning_a_short_answer(self):
        """A partial result is the dangerous case: nine fixes answer, one
        fails, and the response looks like a quieter vehicle."""
        rows = {'u1': [Row('u1', 'in5', '1', '7')], 'u2': []}
        with _Patched():
            with self.assertRaises(ies.IoEventsUnavailable) as caught:
                ies.events_for(FakeSession(rows, fail_uids=['u2']),
                               ['u1', 'u2'])
        self.assertIn('u2', str(caught.exception))


class VendorKey(unittest.TestCase):

    def test_ruptela_gets_the_dot_zero_suffix(self):
        self.assertEqual(ies.vendor_io_id('ruptela', '239'), '239.0')
        self.assertEqual(ies.vendor_io_id('RUPTELA', '239'), '239.0')

    def test_teltonika_is_bare(self):
        self.assertEqual(ies.vendor_io_id('teltonika', '239'), '239')

    def test_any_other_vendor_is_bare_rather_than_a_nameerror(self):
        """The route assigned IO_ID_Found only in the ruptela and teltonika
        branches. The test unit is xirgo_global, so opening the gate raised
        NameError on the first fix."""
        for vendor in ('xirgo_global', 'queclink', '', None, 'unknown'):
            self.assertEqual(ies.vendor_io_id(vendor, 'in5'), 'in5')

    def test_blank_event_uid(self):
        self.assertEqual(ies.vendor_io_id('teltonika', None), '')


class FakeCursor(object):
    def __init__(self, rows=None, raises=False):
        self.rows = rows if rows is not None else []
        self.raises = raises
        self.sql = None
        self.args = None

    def execute(self, sql, args=None):
        if self.raises:
            raise RuntimeError('relation does not exist')
        self.sql, self.args = sql, args

    @property
    def rowcount(self):
        return len(self.rows)

    def fetchall(self):
        return self.rows


class Names(unittest.TestCase):

    def test_resolves_in_a_single_query(self):
        cur = FakeCursor([('in5', 'Ignition'), ('in6', 'Door')])
        got = ies.names_for(cur, 'dll_io_events_config', 'io_display_name',
                            'io_event_vendor_uid', ['in5', 'in6', 'in5'])
        self.assertEqual(got, {'in5': 'Ignition', 'in6': 'Door'})
        self.assertEqual(cur.args, (['in5', 'in6'],),
                         'duplicates must collapse before the query')

    def test_an_empty_reference_table_returns_empty_not_an_error(self):
        """dll_io_events_config holds zero rows today, so every id misses.
        The old code did fetchone()[0] and raised TypeError on None."""
        got = ies.names_for(FakeCursor([]), 'dll_io_events_config',
                            'io_display_name', 'io_event_vendor_uid', ['in5'])
        self.assertEqual(got, {})

    def test_a_broken_reference_table_does_not_fail_the_request(self):
        got = ies.names_for(FakeCursor(raises=True), 'dll_io_events_config',
                            'io_display_name', 'io_event_vendor_uid', ['in5'])
        self.assertEqual(got, {})

    def test_no_keys_asks_nothing(self):
        cur = FakeCursor([('in5', 'Ignition')])
        self.assertEqual(ies.names_for(cur, 't', 'v', 'k', []), {})
        self.assertIsNone(cur.sql)

    def test_null_names_are_dropped(self):
        got = ies.names_for(FakeCursor([('in5', None), ('in6', 'Door')]),
                            't', 'v', 'k', ['in5', 'in6'])
        self.assertEqual(got, {'in6': 'Door'})


if __name__ == '__main__':
    unittest.main(verbosity=2)
