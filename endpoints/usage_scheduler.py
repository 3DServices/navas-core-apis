"""
The nightly daily-token-usage reading (migration 049).

A day's usage is that day's reading of each token account's running total
minus the day before's (token_usage.py). GET /tokens/<client>/usage/daily
takes a reading for the wallet it is asked about, but a wallet nobody opens
gets none, and its next day then reads as unknown. This takes a reading of
every wallet once a night, close to midnight Africa/Kampala.

On by default, unlike app.py's other schedulers, because the OLIWA
dashboard's token runway and daily usage are wrong without it, and it is
harmless to repeat: each reading is an upsert per (wallet, account, day), so
several gunicorn workers each running it at 23:55 write the same rows.

  TOKEN_USAGE_SNAPSHOT_ENABLED   "false" turns it off (e.g. when an external
                                 cron calls POST /tokens/usage/snapshot/run
                                 with X-Service-Key instead)
  TOKEN_USAGE_SNAPSHOT_AT        "HH:MM", Kampala time; default 23:55
"""

import logging
import os
from zoneinfo import ZoneInfo

from . import token_usage

log = logging.getLogger('token_usage')

KAMPALA = ZoneInfo('Africa/Kampala')
JOB_ID = 'token_usage_nightly_snapshot'

# A server that was busy or restarting at 23:55 still takes the reading if it
# is back within this long — late is better than a day with no reading.
MISFIRE_GRACE_SECONDS = 30 * 60


def start_nightly_snapshot(app, run=None, environ=None, scheduler=None):
    """Schedule the nightly reading; returns the scheduler, or None when it is
    off. `run` (default: snapshot_all) and `scheduler` are for tests."""
    env = os.environ if environ is None else environ
    if str(env.get('TOKEN_USAGE_SNAPSHOT_ENABLED', 'true')).lower() == 'false':
        return None
    # Under the Werkzeug debug reloader, only start in the child process.
    if env.get('WERKZEUG_RUN_MAIN') == 'false':
        return None

    hour, minute = token_usage.snapshot_at(env.get('TOKEN_USAGE_SNAPSHOT_AT'))
    if run is None:
        from .tokens_usage_routes import snapshot_all as run

    def job():
        with app.app_context():
            try:
                result = run()
                print(f"[usage] nightly reading {result['day']}: "
                      f"{result['accounts']} token accounts")
            except Exception as error:      # noqa: BLE001
                log.exception('nightly token usage reading failed: %s', error)

    if scheduler is None:
        from apscheduler.schedulers.background import BackgroundScheduler
        scheduler = BackgroundScheduler(daemon=True, timezone=KAMPALA)
    from apscheduler.triggers.cron import CronTrigger
    scheduler.add_job(
        job,
        CronTrigger(hour=hour, minute=minute, timezone=KAMPALA),
        id=JOB_ID,
        replace_existing=True,
        coalesce=True,
        misfire_grace_time=MISFIRE_GRACE_SECONDS,
    )
    if not scheduler.running:
        scheduler.start()
    print(f"[usage] nightly token usage reading scheduled for "
          f"{hour:02d}:{minute:02d} Africa/Kampala")
    return scheduler
