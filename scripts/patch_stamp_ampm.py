#!/usr/bin/env python3
"""The heartbeat clock is 12-hour with an AM/PM suffix and no space.

The probe showed it plainly:

    862846042593213   02-10-2026   08:25:50AM   -> 2026-10-02 00:00:00

The probe ran at 08:25:48. That unit reported two seconds later — it is alive
right now — and _stamp threw the time away and fell back to midnight, because
_TIME_FORMATS held only 24-hour patterns. Nothing errored; the answer was just
quietly up to 24 hours wrong.

That matters more than it looks. hours_since_last_report is what Waswa uses to
tell a customer whether their vehicle is reporting, and a unit that last
reported at 08:25 would be described as last reporting at 00:00 — "8 hours
ago" for a unit that is live this second. Waswa would call a healthy vehicle
offline, confidently, with a figure attached.

So: parse 12-hour clocks, with or without the space, with or without seconds.

Also adds the regression test, because this class of bug is invisible until
someone reads a raw value.

Idempotent.
"""
import ast
import io
import sys

FLEET = 'endpoints/waswa_fleet.py'
TESTS = 'tests/test_waswa_fleet.py'

OLD = "_TIME_FORMATS = ('%H:%M:%S', '%H:%M:%S.%f', '%H:%M')"
NEW = ("# 12-hour first: dll_pulse_status_registry writes '08:25:50AM', with no\n"
       "# space before the meridiem. %H would read '08' correctly and then choke\n"
       "# on the 'AM', so the 24-hour patterns must not get first refusal on a\n"
       "# string that ends in one.\n"
       "_TIME_FORMATS = (\n"
       "    '%I:%M:%S%p', '%I:%M:%S %p', '%I:%M%p', '%I:%M %p',\n"
       "    '%H:%M:%S', '%H:%M:%S.%f', '%H:%M',\n"
       ")")

TEST_BLOCK = '''

# ── Reading the clocks the devices actually write ───────────────────────────

def test_a_twelve_hour_heartbeat_keeps_its_time():
    # The exact shape dll_pulse_status_registry was observed holding. Getting
    # this wrong does not error — it silently returns midnight, and Waswa then
    # calls a unit that reported seconds ago "8 hours silent".
    got = _stamp('02-10-2026', '08:25:50AM')
    assert got == datetime(2026, 10, 2, 8, 25, 50), got


def test_pm_is_not_read_as_am():
    assert _stamp('02-10-2026', '08:25:50PM') == datetime(2026, 10, 2, 20, 25, 50)


def test_noon_and_midnight_do_not_swap():
    assert _stamp('02-10-2026', '12:00:00AM') == datetime(2026, 10, 2, 0, 0, 0)
    assert _stamp('02-10-2026', '12:00:00PM') == datetime(2026, 10, 2, 12, 0, 0)


def test_a_twenty_four_hour_clock_still_works():
    assert _stamp('02-10-2026', '14:30:00') == datetime(2026, 10, 2, 14, 30, 0)


def test_the_location_table_date_order_is_day_first():
    # 10-03-2026 is 10 March, not 3 October. Reading it the other way would
    # move a unit's last fix by seven months.
    assert _stamp('10-03-2026', '11:49:10AM') == datetime(2026, 3, 10, 11, 49, 10)


def test_an_unreadable_time_keeps_the_date_rather_than_losing_both():
    assert _stamp('02-10-2026', 'nonsense') == datetime(2026, 10, 2, 0, 0, 0)


def test_an_unreadable_date_is_unknown_not_epoch():
    # None means "we do not know". A zero date would become a unit that last
    # reported in 1970 and a trip 56 years long.
    assert _stamp('nonsense', '08:25:50AM') is None
    assert _stamp(None, '08:25:50AM') is None
'''


def patch_fleet():
    src = io.open(FLEET, encoding='utf-8', newline='').read()
    if "'%I:%M:%S%p'" in src:
        return src, 'already parses 12-hour clocks'
    if OLD not in src:
        return None, '!! _TIME_FORMATS not found verbatim'
    out = src.replace(OLD, NEW, 1)
    ast.parse(out)
    io.open(FLEET, 'w', encoding='utf-8', newline='').write(out)
    return out, '_TIME_FORMATS now reads AM/PM clocks'


def patch_tests():
    src = io.open(TESTS, encoding='utf-8', newline='').read()
    if 'test_a_twelve_hour_heartbeat_keeps_its_time' in src:
        return 'clock tests already present'

    # _stamp is compiled out of the source by _load(); make sure it is exported.
    if "_stamp = NS['_stamp']" not in src:
        anchor = "dispatch = NS['dispatch']"
        if anchor not in src:
            return '!! could not find the NS exports block'
        src = src.replace(anchor, anchor + "\n_stamp = NS['_stamp']", 1)

    marker = "if __name__ == '__main__':"
    at = src.find(marker)
    if at < 0:
        return '!! could not find the test runner block'
    src = src[:at] + TEST_BLOCK.strip('\n') + '\n\n\n' + src[at:]
    ast.parse(src)
    io.open(TESTS, 'w', encoding='utf-8', newline='').write(src)
    return 'added 7 clock regression tests'


def main():
    out, msg = patch_fleet()
    print('  ' + msg)
    if out is None:
        return 1
    print('  ' + patch_tests())
    print('  syntax OK')
    return 0


if __name__ == '__main__':
    sys.exit(main())
