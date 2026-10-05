"""
test_location_store.py — the position reader's logic, without a database.

location_store is about to become the single source of vehicle positions for
trip history, excel, pdf and replay. B1 proves it against the live stores. This
proves the parts B1 cannot isolate: the date arithmetic, the clock parsing, the
dedupe tiebreak and the ordering — the places where a wrong answer looks like a
right one.

location_store imports only datetime, so it loads straight from its path
without Flask, psycopg2 or the Cassandra driver.
"""

import importlib.util
import os
import unittest
from datetime import date, datetime, timedelta

_PATH = os.path.join(os.path.dirname(__file__), '..', 'endpoints',
                     'location_store.py')
_spec = importlib.util.spec_from_file_location('location_store', _PATH)
ls = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ls)


class Row(object):
    """One Cassandra row. Only the attributes location_store reads."""

    def __init__(self, lon, lat, datestamp='15-07-2025',
                 timestamp='08:25:50AM', record_timestamp=None, data_idx=0,
                 imei='867556044727322', speed=0, hdop=None, io_uid=None,
                 place=None, satellites=None, batch_uid=None):
        self.data_device_imei = imei
        self.data_longitude = lon
        self.data_latitude = lat
        self.speed_log = speed
        self.data_hdop = hdop
        self.local_system_datestamp = datestamp
        self.local_system_timestamp = timestamp
        self.record_io_events_uid = io_uid
        self.geocoded_location = place
        self.data_connected_satelites = satellites
        self.batch_uid = batch_uid
        self.data_idx = data_idx
        self.record_timestamp = record_timestamp


class FakeSession(object):
    def __init__(self, rows_by_day=None, fail_on=None, fail_prepare=False):
        self.rows_by_day = rows_by_day or {}
        self.fail_on = fail_on
        self.fail_prepare = fail_prepare
        self.days_queried = []

    def prepare(self, cql):
        if self.fail_prepare:
            raise RuntimeError('prepare refused')
        self.cql = cql
        return 'STATEMENT'

    def execute(self, stmt, params):
        imei, day = params
        self.days_queried.append(day)
        if self.fail_on and day == self.fail_on:
            raise RuntimeError('read timeout')
        return list(self.rows_by_day.get(day, []))


class DaysIn(unittest.TestCase):

    def test_expands_one_day_at_a_time_oldest_first(self):
        days, truncated = ls.days_in('15-07-2025', '18-07-2025')
        self.assertEqual(days, ['15-07-2025', '16-07-2025',
                                '17-07-2025', '18-07-2025'])
        self.assertFalse(truncated)

    def test_single_day_window(self):
        days, truncated = ls.days_in('15-07-2025', '15-07-2025')
        self.assertEqual(days, ['15-07-2025'])
        self.assertFalse(truncated)

    def test_month_boundary_is_calendar_order_not_text_order(self):
        """The trap this function exists for.

        local_system_datestamp is TEXT in DD-MM-YYYY and part of the partition
        key, so '01-09-2025' sorts BEFORE '31-08-2025' as a string. A CQL range
        over it returns the wrong rows and reports nothing wrong. Per-day
        equality is the only form that cannot lie, so the expansion must cross
        the boundary in calendar order.
        """
        days, _ = ls.days_in('30-08-2025', '02-09-2025')
        self.assertEqual(days, ['30-08-2025', '31-08-2025',
                                '01-09-2025', '02-09-2025'])
        self.assertLess(days.index('31-08-2025'), days.index('01-09-2025'))
        # and the text comparison that would have been used is the wrong way round
        self.assertLess('01-09-2025', '31-08-2025')

    def test_year_boundary(self):
        days, _ = ls.days_in('30-12-2025', '02-01-2026')
        self.assertEqual(days, ['30-12-2025', '31-12-2025',
                                '01-01-2026', '02-01-2026'])

    def test_leap_day_is_included(self):
        days, _ = ls.days_in('28-02-2024', '01-03-2024')
        self.assertIn('29-02-2024', days)

    def test_reversed_window_is_swapped_not_empty(self):
        days, _ = ls.days_in('18-07-2025', '15-07-2025')
        self.assertEqual(days[0], '15-07-2025')
        self.assertEqual(days[-1], '18-07-2025')

    def test_span_is_capped_and_says_so(self):
        days, truncated = ls.days_in('01-01-2025', '31-12-2025')
        self.assertEqual(len(days), ls.MAX_DAYS)
        self.assertTrue(truncated, 'a cut span must report that it was cut')

    def test_unparseable_dates_yield_nothing(self):
        self.assertEqual(ls.days_in('not-a-date', '15-07-2025'), ([], False))
        self.assertEqual(ls.days_in(None, None), ([], False))

    def test_accepts_the_other_date_formats(self):
        days, _ = ls.days_in('2025-07-15', '2025-07-16')
        self.assertEqual(days, ['15-07-2025', '16-07-2025'])


class Stamp(unittest.TestCase):

    def test_twelve_hour_morning(self):
        at = ls._stamp('15-07-2025', '08:25:50AM')
        self.assertEqual(at, datetime(2025, 7, 15, 8, 25, 50))

    def test_twelve_hour_afternoon(self):
        """08:25:50PM is 20:25, not 08:25.

        Read with %H this parses to midnight, and a vehicle that reported 39
        seconds ago is described as silent for nine and a half hours.
        """
        at = ls._stamp('15-07-2025', '08:25:50PM')
        self.assertEqual(at, datetime(2025, 7, 15, 20, 25, 50))

    def test_twelve_hour_with_space(self):
        self.assertEqual(ls._stamp('15-07-2025', '08:25:50 PM'),
                         datetime(2025, 7, 15, 20, 25, 50))

    def test_twenty_four_hour_still_works(self):
        self.assertEqual(ls._stamp('15-07-2025', '20:25:50'),
                         datetime(2025, 7, 15, 20, 25, 50))

    def test_noon_and_midnight(self):
        self.assertEqual(ls._stamp('15-07-2025', '12:00:00AM').hour, 0)
        self.assertEqual(ls._stamp('15-07-2025', '12:00:00PM').hour, 12)

    def test_bad_date_is_none_never_epoch(self):
        """A zero date must not become 1970, which would sit at the top of a
        newest-first history and be rendered to a customer."""
        self.assertIsNone(ls._stamp('0000-00-00', '08:25:50AM'))
        self.assertIsNone(ls._stamp(None, '08:25:50AM'))

    def test_bad_time_falls_back_to_midnight_of_the_right_day(self):
        at = ls._stamp('15-07-2025', 'garbage')
        self.assertEqual(at, datetime(2025, 7, 15, 0, 0, 0))


class Unavailable(unittest.TestCase):

    def test_no_session_raises(self):
        with self.assertRaises(ls.PositionsUnavailable):
            ls.fixes(None, '867556044727322', '15-07-2025', '16-07-2025')

    def test_prepare_failure_raises(self):
        with self.assertRaises(ls.PositionsUnavailable):
            ls.fixes(FakeSession(fail_prepare=True), '867556044727322',
                     '15-07-2025', '16-07-2025')

    def test_read_failure_raises_rather_than_returning_what_it_got(self):
        """A partial read is the dangerous case: three of four days succeed and
        the answer looks like a complete, quieter day."""
        session = FakeSession(
            rows_by_day={'15-07-2025': [Row(32.58, 0.34)]},
            fail_on='16-07-2025')
        with self.assertRaises(ls.PositionsUnavailable):
            ls.fixes(session, '867556044727322', '15-07-2025', '16-07-2025')

    def test_empty_imei_returns_empty_without_querying(self):
        session = FakeSession()
        rows, truncated = ls.fixes(session, '  ', '15-07-2025', '16-07-2025')
        self.assertEqual(rows, [])
        self.assertFalse(truncated)
        self.assertEqual(session.days_queried, [])


class Reading(unittest.TestCase):

    def test_queries_each_day_separately(self):
        session = FakeSession()
        ls.fixes(session, '867556044727322', '15-07-2025', '17-07-2025')
        self.assertEqual(session.days_queried,
                         ['15-07-2025', '16-07-2025', '17-07-2025'])

    def test_null_island_and_unparseable_coordinates_are_dropped(self):
        session = FakeSession(rows_by_day={'15-07-2025': [
            Row(0, 0),
            Row(None, 0.34),
            Row('not-a-number', 0.34),
            Row(32.58, 0.34),
        ]})
        rows, _ = ls.fixes(session, '867556044727322',
                           '15-07-2025', '15-07-2025')
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]['lon'], rows[0]['lat']), (32.58, 0.34))

    def test_ordering_follows_record_timestamp_not_data_idx(self):
        """The correction at the centre of this module.

        In Postgres data_idx was a serial, so "highest data_idx" and "newest"
        were the same statement. In Cassandra data_idx is not sequential. These
        three rows carry data_idx in the opposite order to their timestamps; if
        the reader sorted by data_idx the history would be shuffled and no
        error would be raised.
        """
        session = FakeSession(rows_by_day={'15-07-2025': [
            Row(32.51, 0.31, record_timestamp=datetime(2025, 7, 15, 6, 0),
                data_idx=1737047314),
            Row(32.52, 0.32, record_timestamp=datetime(2025, 7, 15, 9, 0),
                data_idx=741899120),
            Row(32.53, 0.33, record_timestamp=datetime(2025, 7, 15, 12, 0),
                data_idx=1645805121),
        ]})
        rows, _ = ls.fixes(session, '867556044727322',
                           '15-07-2025', '15-07-2025')
        self.assertEqual([r['lon'] for r in rows], [32.53, 32.52, 32.51])

    def test_oldest_first_when_asked(self):
        session = FakeSession(rows_by_day={'15-07-2025': [
            Row(32.51, 0.31, record_timestamp=datetime(2025, 7, 15, 6, 0)),
            Row(32.53, 0.33, record_timestamp=datetime(2025, 7, 15, 12, 0)),
        ]})
        rows, _ = ls.fixes(session, '867556044727322', '15-07-2025',
                           '15-07-2025', newest_first=False)
        self.assertEqual([r['lon'] for r in rows], [32.51, 32.53])

    def test_dedupe_keeps_one_per_coordinate_the_latest(self):
        """What PARTITION BY lon, lat ... row_num = 1 did, with
        record_timestamp as the tiebreak instead of data_idx."""
        session = FakeSession(rows_by_day={'15-07-2025': [
            Row(32.58, 0.34, record_timestamp=datetime(2025, 7, 15, 6, 0),
                place='early', data_idx=9999999),
            Row(32.58, 0.34, record_timestamp=datetime(2025, 7, 15, 18, 0),
                place='late', data_idx=1),
        ]})
        rows, _ = ls.fixes(session, '867556044727322',
                           '15-07-2025', '15-07-2025')
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['place'], 'late',
                         'the kept row must be the latest, not the highest data_idx')

    def test_dedupe_can_be_turned_off(self):
        session = FakeSession(rows_by_day={'15-07-2025': [
            Row(32.58, 0.34, record_timestamp=datetime(2025, 7, 15, 6, 0)),
            Row(32.58, 0.34, record_timestamp=datetime(2025, 7, 15, 18, 0)),
        ]})
        rows, _ = ls.fixes(session, '867556044727322', '15-07-2025',
                           '15-07-2025', dedupe_coordinates=False)
        self.assertEqual(len(rows), 2)

    def test_dedupe_spans_days_as_the_sql_did(self):
        session = FakeSession(rows_by_day={
            '15-07-2025': [Row(32.58, 0.34, datestamp='15-07-2025',
                               record_timestamp=datetime(2025, 7, 15, 6, 0))],
            '16-07-2025': [Row(32.58, 0.34, datestamp='16-07-2025',
                               record_timestamp=datetime(2025, 7, 16, 6, 0))],
        })
        rows, _ = ls.fixes(session, '867556044727322',
                           '15-07-2025', '16-07-2025')
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['datestamp'], '16-07-2025')

    def test_limit_and_offset_apply_after_ordering(self):
        session = FakeSession(rows_by_day={'15-07-2025': [
            Row(32.50 + i / 100.0, 0.3,
                record_timestamp=datetime(2025, 7, 15, 6 + i, 0))
            for i in range(5)
        ]})
        rows, _ = ls.fixes(session, '867556044727322', '15-07-2025',
                           '15-07-2025', limit=2, offset=1)
        # newest first: .54 .53 .52 .51 .50 — offset 1, limit 2 -> .53 .52
        self.assertEqual([round(r['lon'], 2) for r in rows], [32.53, 32.52])

    def test_row_index_is_one_based_after_pagination(self):
        session = FakeSession(rows_by_day={'15-07-2025': [
            Row(32.50 + i / 100.0, 0.3,
                record_timestamp=datetime(2025, 7, 15, 6 + i, 0))
            for i in range(5)
        ]})
        rows, _ = ls.fixes(session, '867556044727322', '15-07-2025',
                           '15-07-2025', limit=2, offset=1)
        self.assertEqual([r['row_index'] for r in rows], [1, 2])

    def test_clock_window_filters_within_the_day(self):
        session = FakeSession(rows_by_day={'15-07-2025': [
            Row(32.51, 0.31, timestamp='06:00:00AM'),
            Row(32.52, 0.32, timestamp='10:00:00AM'),
            Row(32.53, 0.33, timestamp='08:00:00PM'),
        ]})
        rows, _ = ls.fixes(session, '867556044727322', '15-07-2025',
                           '15-07-2025', time_from='07:00:00AM',
                           time_to='12:00:00PM')
        self.assertEqual([r['lon'] for r in rows], [32.52])

    def test_truncated_flag_survives_to_the_caller(self):
        session = FakeSession()
        rows, truncated = ls.fixes(session, '867556044727322',
                                   '01-01-2025', '31-12-2025')
        self.assertTrue(truncated)
        self.assertEqual(len(session.days_queried), ls.MAX_DAYS)


class TupleContract(unittest.TestCase):
    """data.py indexes these positionally. The orders are the contract."""

    def _one_row(self):
        session = FakeSession(rows_by_day={'15-07-2025': [
            Row(32.58, 0.34, datestamp='15-07-2025', timestamp='08:25:50AM',
                record_timestamp=datetime(2025, 7, 15, 5, 25, 50),
                data_idx=4242, speed=37, hdop=0.9, io_uid='io-1',
                place='Ntinda', satellites=11, batch_uid='b-1')
        ]})
        rows, _ = ls.fixes(session, '867556044727322',
                           '15-07-2025', '15-07-2025')
        return rows[0]

    def test_history_tuple_is_twelve_wide_in_order(self):
        t = ls.as_history_tuple(self._one_row())
        self.assertEqual(len(t), 12)
        self.assertEqual(t[0], 32.58)      # lon
        self.assertEqual(t[1], 0.34)       # lat
        self.assertEqual(t[2], 37)         # speed
        self.assertEqual(t[3], 0.9)        # hdop
        self.assertEqual(t[4], '15-07-2025')   # datestamp
        self.assertEqual(t[5], 'io-1')     # record_io_events_uid
        self.assertEqual(t[6], 'Ntinda')   # geocoded_location
        self.assertEqual(t[7], '08:25:50AM')   # timestamp
        self.assertEqual(t[8], 11)         # satellites
        self.assertEqual(t[9], 'b-1')      # batch_uid
        self.assertEqual(t[10], 4242)      # data_idx
        self.assertEqual(t[11], 1)         # row_index

    def test_history_tuple_covers_every_index_data_py_reads(self):
        """All five history-shaped call sites in data.py read trip[0]..trip[10].
        Index 11 is selected by the old SQL and never read."""
        t = ls.as_history_tuple(self._one_row())
        for i in range(11):
            self.assertLess(i, len(t))

    def test_replay_tuple_matches_the_dataframe_columns(self):
        """trips/history/replay feeds this straight into
        pd.DataFrame(columns=['Device', 'Trip Location', 'Longitude
        Cordinates', 'Latitude Cordinates', 'Moving Speed ( KM/H )',
        'Trip Date', 'Trip Time', 'Satelites Available'])."""
        t = ls.as_replay_tuple(self._one_row())
        self.assertEqual(len(t), 8)
        self.assertEqual(t[0], '867556044727322')  # Device
        self.assertEqual(t[1], 'Ntinda')           # Trip Location
        self.assertEqual(t[2], 32.58)              # Longitude
        self.assertEqual(t[3], 0.34)               # Latitude
        self.assertEqual(t[4], 37)                 # Speed
        self.assertEqual(t[5], '15-07-2025')       # Trip Date
        self.assertEqual(t[6], '08:25:50AM')       # Trip Time
        self.assertEqual(t[7], 11)                 # Satellites

    def test_local_and_utc_are_both_kept(self):
        row = self._one_row()
        self.assertEqual(row['at'], datetime(2025, 7, 15, 8, 25, 50))
        self.assertEqual(row['at_utc'], datetime(2025, 7, 15, 5, 25, 50))


if __name__ == '__main__':
    unittest.main(verbosity=2)


# ─────────────────────────────────────────────────────────────────────────────
# The newest-first early stop.
#
# fixes() used to read every day in the window, then dedupe, sort and slice.
# On the busiest unit measured — 13,407 fixes a day — a 92-day span meant
# 1.2 million dicts in a worker to answer a page needing one or two days.
#
# It now reads days newest first and stops when the page is full. That is only
# safe because local days occupy adjacent, non-overlapping UTC ranges (EAT is
# a fixed +3), so walking backwards visits fixes in strictly descending time
# order and first-seen-wins picks exactly the row the dedupe would have kept.
#
# These tests exist to prove the optimisation changed nothing the caller can
# see. The equivalence test re-implements the OLD algorithm and compares,
# because "it looks right" is how trip history started lying in the first
# place.
# ─────────────────────────────────────────────────────────────────────────────

def local_utc(day, hour, minute=0, second=0):
    """The UTC stamp a device in EAT would write for a local wall time.

    Local day D runs UTC [D-1 21:00, D 21:00). The early stop depends on that
    invariant, so the fixtures have to honour it rather than inventing stamps.
    """
    local = datetime(day.year, day.month, day.day, hour, minute, second)
    return local - timedelta(hours=3)


def day_of(n):
    return date(2026, 10, n)


def make_day(n, coords, start_hour=6):
    """Rows for one local day: one fix per coordinate, an hour apart."""
    d = day_of(n)
    label = d.strftime('%d-%m-%Y')
    out = []
    for i, (lon, lat) in enumerate(coords):
        hour = start_hour + i
        out.append(Row(lon, lat, datestamp=label,
                       timestamp=f'{hour if hour <= 12 else hour - 12:02d}:'
                                 f'00:00{"AM" if hour < 12 else "PM"}',
                       record_timestamp=local_utc(d, hour),
                       data_idx=99999 - i * 7, place=f'{label} #{i}'))
    return label, out


def reference_fixes(rows_by_day, days, limit=None, offset=0,
                    dedupe=True, newest_first=True):
    """The algorithm fixes() used BEFORE the early stop: read every day, then
    dedupe, sort and slice. Written out here so the new code is compared
    against the old behaviour rather than against itself."""
    rows = []
    for label in days:
        for r in rows_by_day.get(label, []):
            lon = ls._num(r.data_longitude)
            lat = ls._num(r.data_latitude)
            if lon is None or lat is None or (lon == 0 and lat == 0):
                continue
            rows.append({'lon': lon, 'lat': lat,
                         'at': ls._stamp(r.local_system_datestamp,
                                         r.local_system_timestamp),
                         'at_utc': r.record_timestamp,
                         'place': r.geocoded_location})
    key = lambda row: (row['at_utc'] or row['at'] or datetime.min)  # noqa: E731
    if dedupe:
        best = {}
        for row in rows:
            k = (row['lon'], row['lat'])
            if k not in best or key(row) > key(best[k]):
                best[k] = row
        rows = list(best.values())
    rows.sort(key=key, reverse=newest_first)
    start = max(0, offset)
    if limit is not None:
        rows = rows[start:start + max(0, limit)]
    elif start:
        rows = rows[start:]
    return [(r['lon'], r['lat'], r['place']) for r in rows]


class EarlyStop(unittest.TestCase):

    def setUp(self):
        # Five days. Some coordinates recur across days, which is what makes
        # first-seen-wins non-trivial: the dedupe must keep the NEWEST.
        self.rows_by_day = {}
        self.labels = []
        plan = {
            1: [(32.01, 0.1), (32.02, 0.2), (32.03, 0.3)],
            2: [(32.02, 0.2), (32.04, 0.4)],
            3: [(32.05, 0.5), (32.06, 0.6), (32.01, 0.1)],
            4: [(32.07, 0.7)],
            5: [(32.08, 0.8), (32.09, 0.9), (32.03, 0.3), (32.10, 1.0)],
        }
        for n in sorted(plan):
            label, rows = make_day(n, plan[n])
            self.rows_by_day[label] = rows
            self.labels.append(label)

    def session(self):
        return FakeSession(rows_by_day=self.rows_by_day)

    def ask(self, **kw):
        s = self.session()
        rows, truncated = ls.fixes(s, '867556044727322',
                                   '01-10-2026', '05-10-2026', **kw)
        return s, [(r['lon'], r['lat'], r['place']) for r in rows], truncated

    def test_matches_the_old_algorithm_for_every_page(self):
        for limit in (1, 2, 3, 5, 8, 20):
            for offset in (0, 1, 2, 4, 9):
                _s, got, _t = self.ask(limit=limit, offset=offset)
                want = reference_fixes(self.rows_by_day, self.labels,
                                       limit=limit, offset=offset)
                self.assertEqual(got, want,
                                 f'limit={limit} offset={offset}')

    def test_matches_the_old_algorithm_without_dedupe(self):
        for limit in (1, 4, 11):
            _s, got, _t = self.ask(limit=limit, dedupe_coordinates=False)
            want = reference_fixes(self.rows_by_day, self.labels,
                                   limit=limit, dedupe=False)
            self.assertEqual(got, want, f'limit={limit}')

    def test_reads_days_newest_first(self):
        s, _got, _t = self.ask(limit=1)
        self.assertEqual(s.days_queried[0], '05-10-2026',
                         'paging must start at the newest day')

    def test_stops_before_reading_the_whole_window(self):
        s, got, _t = self.ask(limit=2)
        self.assertEqual(len(got), 2)
        self.assertLess(len(s.days_queried), len(self.labels),
                        'a 2-row page must not read all five days')

    def test_a_full_page_still_reads_everything_it_needs(self):
        _s, got, _t = self.ask(limit=50)
        want = reference_fixes(self.rows_by_day, self.labels, limit=50)
        self.assertEqual(got, want)
        self.assertEqual(len(got), 10, 'ten distinct coordinates in all')

    def test_recurring_coordinate_keeps_its_newest_fix(self):
        """(32.03, 0.3) appears on day 1 and day 5. The kept row must be the
        day-5 one — the case first-seen-wins exists to get right."""
        _s, got, _t = self.ask(limit=50)
        places = {(lon, lat): place for lon, lat, place in got}
        self.assertEqual(places[(32.03, 0.3)], '05-10-2026 #2')
        self.assertEqual(places[(32.01, 0.1)], '03-10-2026 #2')
        self.assertEqual(places[(32.02, 0.2)], '02-10-2026 #0')

    def test_oldest_first_reads_every_day_and_is_still_correct(self):
        """newest_first=False cannot use the early stop: walking oldest first
        would make first-seen the earliest fix, and the dedupe keeps the
        latest. It must fall back to reading the window."""
        s = self.session()
        rows, _t = ls.fixes(s, '867556044727322', '01-10-2026', '05-10-2026',
                            limit=3, newest_first=False)
        got = [(r['lon'], r['lat'], r['place']) for r in rows]
        want = reference_fixes(self.rows_by_day, self.labels, limit=3,
                               newest_first=False)
        self.assertEqual(got, want)
        self.assertEqual(len(s.days_queried), len(self.labels))

    def test_no_limit_reads_every_day(self):
        s = self.session()
        rows, _t = ls.fixes(s, '867556044727322', '01-10-2026', '05-10-2026')
        self.assertEqual(len(s.days_queried), len(self.labels))
        self.assertEqual(len(rows), 10)

    def test_row_index_restarts_at_one_on_every_page(self):
        s = self.session()
        rows, _t = ls.fixes(s, '867556044727322', '01-10-2026', '05-10-2026',
                            limit=3, offset=4)
        self.assertEqual([r['row_index'] for r in rows], [1, 2, 3])

    def test_unbounded_request_over_the_ceiling_raises(self):
        """A caller with no limit must be refused loudly rather than quietly
        filling a worker's memory."""
        big = {}
        for n in range(1, 4):
            d = day_of(n).strftime('%d-%m-%Y')
            big[d] = [Row(32.0 + i / 1e6, 0.1, datestamp=d,
                          record_timestamp=local_utc(day_of(n), 6))
                      for i in range(ls.MAX_ROWS // 2 + 10)]
        with self.assertRaises(ls.PositionsUnavailable) as caught:
            ls.fixes(FakeSession(rows_by_day=big), '867556044727322',
                     '01-10-2026', '03-10-2026')
        self.assertIn('shorter range', str(caught.exception))

    def test_the_same_request_with_a_limit_does_not_raise(self):
        """The ceiling must not punish the paged case the early stop protects."""
        big = {}
        for n in range(1, 4):
            d = day_of(n).strftime('%d-%m-%Y')
            big[d] = [Row(32.0 + i / 1e6, 0.1, datestamp=d,
                          record_timestamp=local_utc(day_of(n), 6))
                      for i in range(ls.MAX_ROWS // 2 + 10)]
        rows, _t = ls.fixes(FakeSession(rows_by_day=big), '867556044727322',
                            '01-10-2026', '03-10-2026', limit=20)
        self.assertEqual(len(rows), 20)

    def test_clock_window_still_applies_under_the_early_stop(self):
        s = self.session()
        rows, _t = ls.fixes(s, '867556044727322', '01-10-2026', '05-10-2026',
                            limit=50, time_from='09:00:00AM',
                            time_to='11:59:59AM')
        for r in rows:
            self.assertGreaterEqual(r['at'].hour, 9)
            self.assertLessEqual(r['at'].hour, 11)

    def test_a_read_failure_on_a_newer_day_still_raises(self):
        """The early stop must not turn a failed read into a short page."""
        session = FakeSession(rows_by_day=self.rows_by_day,
                             fail_on='05-10-2026')
        with self.assertRaises(ls.PositionsUnavailable):
            ls.fixes(session, '867556044727322', '01-10-2026', '05-10-2026',
                     limit=2)
