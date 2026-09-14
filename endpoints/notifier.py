"""
notifier.py — lightweight multi-channel notification helper.

One entry point, `notify()`, so callers (e.g. the auto-renew worker) don't care
HOW a message is delivered. Phase 1 implements the in-app channel by inserting a
row into dll_event_notifications (the same table the mobile Alerts/notifications
list reads). The push / SMS / WhatsApp / email channels are adapter stubs: they
log that the message was queued so the pipeline is in place, but no external
provider is called until credentials/adapters are wired in a later phase.

All functions are best-effort and must never raise into the caller.
"""

import json
import logging
import uuid

_logger = logging.getLogger("notifier")

# Channels understood by the settings/UI. in_app is delivered now; the rest are
# accepted and queued (logged) until their provider adapters are implemented.
KNOWN_CHANNELS = {"in_app", "push", "sms", "whatsapp", "email"}


def parse_channels(raw):
    """Accepts a csv string or list; returns a clean list of known channels."""
    if not raw:
        return ["in_app"]
    if isinstance(raw, str):
        parts = [p.strip().lower() for p in raw.split(",")]
    elif isinstance(raw, (list, tuple)):
        parts = [str(p).strip().lower() for p in raw]
    else:
        return ["in_app"]
    chans = [p for p in parts if p in KNOWN_CHANNELS]
    return chans or ["in_app"]


def _deliver_in_app(cur, owner_uid, title, body, category):
    """Insert an in-app notification into dll_event_notifications."""
    cur.execute(
        """
        INSERT INTO dll_event_notifications
            (notification_uid, event_uid, event_name, device_imei, device_name,
             condition, trigger_value, geozone_name, breach_type, alert_channels,
             owner_uid, is_read, date_triggered)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, FALSE, NOW())
        """,
        (
            str(uuid.uuid4()),
            f"auto_renew:{category}",  # synthetic event_uid
            title,
            "", "",
            category,
            body,
            "", "",
            json.dumps(["in_app"]),
            str(owner_uid),
        ),
    )


def notify(cur, owner_uid, title, body, category, channels):
    """Send a notification across [channels] for [owner_uid]. Best-effort.

    cur      : an open psycopg2 cursor (caller owns the transaction)
    category : short machine tag, e.g. 'usage', 'low_balance', 'top_up', 'renewed'
    channels : csv string or list; unknown channels are ignored
    """
    chans = parse_channels(channels)
    for ch in chans:
        try:
            if ch == "in_app":
                _deliver_in_app(cur, owner_uid, title, body, category)
            else:
                # Adapter not yet configured — queue/log so the pipeline is visible.
                _logger.info(
                    "[notify:%s] queued for %s (adapter not configured): %s — %s",
                    ch, owner_uid, title, body,
                )
        except Exception as e:  # pragma: no cover - notifications must not break callers
            _logger.warning("[notify:%s] failed for %s: %s", ch, owner_uid, e)
