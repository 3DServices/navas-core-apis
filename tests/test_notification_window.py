# -*- coding: utf-8 -*-
"""Tests for endpoints/notification_window.py

notification_window.py is pure, so it imports directly -- no Flask, no
database.

Run:  python tests/test_notification_window.py
"""

import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'endpoints'))

import notification_window as nw                          # noqa: E402

RESULTS = []


def eq(name, got, want):
    RESULTS.append((name, got == want, 'got %r, want %r' % (got, want)))


def raises(name, value):
    try:
        nw.window(value)
    except nw.BadSince:
        RESULTS.append((name, True, ''))
        return
    RESULTS.append((name, False, 'no BadSince for %r' % (value,)))


eq('no since: the latest 200, as before', nw.window(None), (None, nw.LATEST))
eq('an empty since is no since', nw.window('  '), (None, 200))

eq('a date means its midnight',
   nw.window('2026-10-08'), (datetime(2026, 10, 8), nw.SINCE_CAP))
eq('a date and time, with a space',
   nw.window('2026-10-08 06:30:00'), (datetime(2026, 10, 8, 6, 30), 5000))
eq('a date and time, ISO T',
   nw.window('2026-10-08T06:30:00'), (datetime(2026, 10, 8, 6, 30), 5000))

# Stored stamps are Kampala local time (UTC+3) without a zone.
eq('UTC is moved to Kampala time',
   nw.window('2026-10-08T03:00:00Z')[0], datetime(2026, 10, 8, 6, 0))
eq('an offset is moved to Kampala time',
   nw.window('2026-10-08T06:00:00+03:00')[0], datetime(2026, 10, 8, 6, 0))

raises('words are refused', 'last week')
raises('a half date is refused', '2026-10')
raises('an impossible date is refused', '2026-13-40')


if __name__ == '__main__':
    failed = [r for r in RESULTS if not r[1]]
    for name, ok, detail in RESULTS:
        print('%s  %s%s' % ('PASS' if ok else 'FAIL', name,
                            '' if ok else '  -- ' + detail))
    print('\n%d passed, %d failed' % (len(RESULTS) - len(failed), len(failed)))
    sys.exit(1 if failed else 0)
