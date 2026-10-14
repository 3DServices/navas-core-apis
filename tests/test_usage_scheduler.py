# -*- coding: utf-8 -*-
"""Tests for endpoints/usage_scheduler.py — the nightly token usage reading.

Runs a real APScheduler (paused, so nothing fires) with a stand-in for the
database work, so it needs the API's virtualenv but no database.

Run:  .venv/Scripts/python tests/test_usage_scheduler.py
"""

import contextlib
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from apscheduler.schedulers.background import BackgroundScheduler  # noqa: E402

from endpoints import token_usage                                    # noqa: E402
from endpoints import usage_scheduler as us                          # noqa: E402

RESULTS = []


def eq(name, got, want):
    RESULTS.append((name, got == want, 'got %r, want %r' % (got, want)))


class FakeApp:
    def __init__(self):
        self.contexts = 0

    @contextlib.contextmanager
    def app_context(self):
        self.contexts += 1
        yield


def paused():
    """A scheduler that is running but fires nothing, so start() is skipped
    and no job runs on its own during the test."""
    s = BackgroundScheduler(timezone=us.KAMPALA)
    s.start(paused=True)
    return s


def schedule(env, run=None, app=None):
    s = paused()
    got = us.start_nightly_snapshot(app or FakeApp(), run=run or (lambda: None),
                                    environ=env, scheduler=s)
    return s, got


# ── when it is scheduled ───────────────────────────────────────────────────

s, got = schedule({})
job = s.get_job(us.JOB_ID)
eq('on by default', got is s and job is not None, True)
fields = {f.name: str(f) for f in job.trigger.fields}
eq('at 23:55', (fields['hour'], fields['minute']), ('23', '55'))
eq('in Kampala time', str(job.trigger.timezone), 'Africa/Kampala')
nxt = job.trigger.get_next_fire_time(None, datetime(2026, 10, 14, 12, 0, tzinfo=us.KAMPALA))
eq('next run: tonight 23:55 Kampala',
   nxt.replace(tzinfo=None), datetime(2026, 10, 14, 23, 55))
nxt = job.trigger.get_next_fire_time(None, datetime(2026, 10, 14, 23, 56, tzinfo=us.KAMPALA))
eq('just after it ran: tomorrow night', nxt.replace(tzinfo=None),
   datetime(2026, 10, 15, 23, 55))
eq('a missed run still happens within the grace period',
   job.misfire_grace_time, us.MISFIRE_GRACE_SECONDS)
eq('missed runs collapse into one', job.coalesce, True)
s.shutdown(wait=False)

s, _ = schedule({'TOKEN_USAGE_SNAPSHOT_AT': '06:30'})
fields = {f.name: str(f) for f in s.get_job(us.JOB_ID).trigger.fields}
eq('the time can be moved', (fields['hour'], fields['minute']), ('6', '30'))
s.shutdown(wait=False)

s, got = schedule({'TOKEN_USAGE_SNAPSHOT_ENABLED': 'false'})
eq('can be switched off', (got, s.get_jobs()), (None, []))
s.shutdown(wait=False)

s, got = schedule({'WERKZEUG_RUN_MAIN': 'false'})
eq('not in the debug reloader\'s parent process', got, None)
s.shutdown(wait=False)

s, _ = schedule({})
us.start_nightly_snapshot(FakeApp(), run=lambda: None, environ={}, scheduler=s)
eq('starting twice keeps one job', len(s.get_jobs()), 1)
s.shutdown(wait=False)

# ── what the job does ──────────────────────────────────────────────────────

calls = []
app = FakeApp()
s, _ = schedule({}, run=lambda: calls.append(1) or {'day': '2026-10-14', 'accounts': 3},
                app=app)
s.get_job(us.JOB_ID).func()
eq('runs the reading inside the app context', (len(calls), app.contexts), (1, 1))
s.shutdown(wait=False)


def boom():
    raise RuntimeError('database down')


s, _ = schedule({}, run=boom)
try:
    s.get_job(us.JOB_ID).func()
    eq('a failed reading is logged, never raised into the scheduler', True, True)
except Exception as error:      # noqa: BLE001
    eq('a failed reading is logged, never raised into the scheduler', repr(error), None)
s.shutdown(wait=False)

# ── the time setting ───────────────────────────────────────────────────────

eq('HH:MM', token_usage.snapshot_at('06:30'), (6, 30))
eq('empty: 23:55', token_usage.snapshot_at(''), (23, 55))
eq('not a time: 23:55', token_usage.snapshot_at('midnight'), (23, 55))
eq('out of range: 23:55', token_usage.snapshot_at('25:00'), (23, 55))


if __name__ == '__main__':
    failed = [r for r in RESULTS if not r[1]]
    for name, ok, detail in RESULTS:
        print('%s  %s%s' % ('PASS' if ok else 'FAIL', name,
                            '' if ok else '  -- ' + detail))
    print('\n%d passed, %d failed' % (len(RESULTS) - len(failed), len(failed)))
    sys.exit(1 if failed else 0)
