"""
permit_reminders -- tells a client when a driver's permit is about to expire.

Every client gets these; there is no rule to set up. Each driver who may drive
(driver_rules.REMINDED_STATUSES) is reminded once at each stage of
driver_rules.REMINDER_DAYS -- 30, 14, 7 and 1 days before, and when it
expires. What was sent is kept in dll_driver_permit_reminders (migration 056),
so a stage is never sent twice, and a renewed permit starts again.

The reminder is an alert in the client's list (dll_event_notifications), the
same list the console and the app read: condition 'permit_expiring', the
driver's name where a vehicle's would be, and their current vehicle's IMEI if
they have one.

Run by the alert sweep (alert_engine.run_alert_sweep), so it runs whenever
the alert engine does. Checking every few minutes is cheap: one query, and
nothing is written until a driver reaches a new stage.
"""

import json
import uuid
from datetime import timedelta

from . import driver_rules as rules
from .owner_root import client_root

CONDITION = 'permit_expiring'


def tables_ready(cur):
    cur.execute("SELECT to_regclass('dll_driver_permit_reminders') AS t")
    row = cur.fetchone()
    return bool(row and row['t'])


def due_drivers(cur, today):
    """Drivers whose permit is within the first reminder stage or past it,
    with the last reminder sent for them."""
    cur.execute(
        """SELECT d.driver_uid, d.client_uid, d.full_name, d.permit_expiry,
                  a.device_imei AS current_imei,
                  r.permit_expiry AS sent_for, r.stage AS sent_stage
             FROM dll_drivers d
             LEFT JOIN dll_driver_assignments a
               ON a.driver_uid = d.driver_uid AND a.ended_at IS NULL
             LEFT JOIN dll_driver_permit_reminders r
               ON r.driver_uid = d.driver_uid
            WHERE d.status = ANY(%s) AND d.permit_expiry <= %s""",
        (list(rules.REMINDED_STATUSES),
         today + timedelta(days=rules.REMINDER_DAYS[0])))
    return cur.fetchall()


def write_reminder(cur, driver, title, sentence):
    cur.execute(
        """INSERT INTO dll_event_notifications
               (notification_uid, event_uid, event_name, device_imei, device_name,
                condition, trigger_value, geozone_name, breach_type, alert_channels,
                owner_uid, is_read, date_triggered)
           VALUES (%s, %s, %s, %s, %s, %s, %s, '', '', %s, %s, FALSE, NOW())""",
        (str(uuid.uuid4()), f"driver_permit:{driver['driver_uid']}", title,
         driver.get('current_imei') or '', driver['full_name'], CONDITION,
         sentence, json.dumps(['in_app']),
         client_root(cur, driver['client_uid'])))


def remember(cur, driver, stage):
    cur.execute(
        """INSERT INTO dll_driver_permit_reminders
               (driver_uid, permit_expiry, stage, sent_at)
           VALUES (%s, %s, %s, NOW())
           ON CONFLICT (driver_uid) DO UPDATE
              SET permit_expiry = EXCLUDED.permit_expiry,
                  stage = EXCLUDED.stage, sent_at = NOW()""",
        (driver['driver_uid'], driver['permit_expiry'], stage))


def send_reminders(cur, today, live=True):
    """Send the reminders due today. Returns {'checked', 'sent', 'by_stage'}.
    live=False works out what would be sent and writes nothing. The caller
    owns the transaction."""
    summary = {'checked': 0, 'sent': 0, 'by_stage': {}}
    for driver in due_drivers(cur, today):
        summary['checked'] += 1
        stage = rules.reminder_due(driver['permit_expiry'], today,
                                   driver.get('sent_for'), driver.get('sent_stage'))
        if stage is None:
            continue
        summary['sent'] += 1
        key = 'expired' if stage == 0 and driver['permit_expiry'] < today else str(stage)
        summary['by_stage'][key] = summary['by_stage'].get(key, 0) + 1
        if live:
            title, sentence = rules.reminder_message(
                driver['full_name'], driver['permit_expiry'], today)
            write_reminder(cur, driver, title, sentence)
            remember(cur, driver, stage)
    return summary
