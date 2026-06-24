from flask import Flask
from flask import Blueprint
from flask import request
import psycopg2
from flask import json
from flask import jsonify
import datetime
import random
from flask import current_app
import base64
from decimal import Decimal
from .globals import reply
import base64
from .globals import check_device
import uuid

device_eventsbp = Blueprint("Device Events", __name__)


# ── Notification Logging & History ──────────────────────────────────────────
#
# Table: dll_event_notifications
# CREATE TABLE IF NOT EXISTS dll_event_notifications (
#     notification_uid   VARCHAR(64) PRIMARY KEY,
#     event_uid          VARCHAR(64) NOT NULL,
#     event_name         VARCHAR(256),
#     device_imei        VARCHAR(64),
#     device_name        VARCHAR(256),
#     condition          VARCHAR(64),
#     trigger_value      TEXT,
#     geozone_name       VARCHAR(256),
#     breach_type        VARCHAR(16),
#     alert_channels     TEXT,
#     owner_uid          VARCHAR(64) NOT NULL,
#     is_read            BOOLEAN DEFAULT FALSE,
#     date_triggered     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
# );
# CREATE INDEX idx_notif_owner ON dll_event_notifications(owner_uid);
# CREATE INDEX idx_notif_event ON dll_event_notifications(event_uid);


@device_eventsbp.route("/notifications/log", methods=["POST"])
def log_notification():
    """Log a triggered event notification."""
    try:
        data = request.get_json()
        if not data:
            return reply("error", 400, "No data provided", "")

        notification_uid = str(uuid.uuid4())
        event_uid = data.get("event_uid", "")
        event_name = data.get("event_name", "")
        device_imei = data.get("device_imei", "")
        device_name = data.get("device_name", "")
        condition = data.get("condition", "")
        trigger_value = data.get("trigger_value", "")
        geozone_name = data.get("geozone_name", "")
        breach_type = data.get("breach_type", "")
        alert_channels = json.dumps(data.get("alert_channels", []))
        owner_uid = data.get("owner_uid", "")

        if not event_uid or not owner_uid:
            return reply("error", 400, "event_uid and owner_uid are required", "")

        dbconnect = psycopg2.connect(current_app.config['db_link'])
        cur = dbconnect.cursor()

        cur.execute("""
            INSERT INTO dll_event_notifications
                (notification_uid, event_uid, event_name, device_imei, device_name,
                 "condition", trigger_value, geozone_name, breach_type, alert_channels,
                 owner_uid, is_read, date_triggered)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, FALSE, NOW())
        """, (
            notification_uid, event_uid, event_name, device_imei, device_name,
            condition, trigger_value, geozone_name, breach_type, alert_channels,
            owner_uid,
        ))
        dbconnect.commit()
        cur.close()
        dbconnect.close()

        return reply("success", 200, "Notification logged", notification_uid)

    except Exception as e:
        return reply("error", 500, f"Error logging notification: {str(e)}", "")


@device_eventsbp.route("/notifications/<owner_uid>/list", methods=["GET"])
def get_notifications(owner_uid):
    """Fetch notification history for an owner, most recent first."""
    try:
        dbconnect = psycopg2.connect(current_app.config['db_link'])
        cur = dbconnect.cursor()

        cur.execute("""
            SELECT notification_uid, event_uid, event_name, device_imei, device_name,
                   "condition", trigger_value, geozone_name, breach_type, alert_channels,
                   is_read, date_triggered
            FROM dll_event_notifications
            WHERE owner_uid = %s
            ORDER BY date_triggered DESC
            LIMIT 200
        """, (owner_uid,))

        rows = cur.fetchall()
        cur.close()
        dbconnect.close()

        notifications = []
        for row in rows:
            notifications.append({
                "notification_uid": row[0],
                "event_uid": row[1],
                "event_name": row[2],
                "device_imei": row[3],
                "device_name": row[4],
                "condition": row[5],
                "trigger_value": row[6],
                "geozone_name": row[7],
                "breach_type": row[8],
                "alert_channels": row[9],
                "is_read": row[10],
                "date_triggered": row[11].strftime("%Y-%m-%d %H:%M:%S") if row[11] else "",
            })

        return reply("success", 200, "Notifications loaded", notifications)

    except Exception as e:
        return reply("error", 500, f"Error fetching notifications: {str(e)}", "")


@device_eventsbp.route("/notifications/<notification_uid>/read", methods=["PUT"])
def mark_notification_read(notification_uid):
    """Mark a single notification as read."""
    try:
        dbconnect = psycopg2.connect(current_app.config['db_link'])
        cur = dbconnect.cursor()

        cur.execute("""
            UPDATE dll_event_notifications
            SET is_read = TRUE
            WHERE notification_uid = %s
        """, (notification_uid,))
        dbconnect.commit()
        cur.close()
        dbconnect.close()

        return reply("success", 200, "Notification marked as read", "")

    except Exception as e:
        return reply("error", 500, f"Error updating notification: {str(e)}", "")


@device_eventsbp.route("/notifications/<owner_uid>/unread-count", methods=["GET"])
def get_unread_count(owner_uid):
    """Get the count of unread notifications for an owner."""
    try:
        dbconnect = psycopg2.connect(current_app.config['db_link'])
        cur = dbconnect.cursor()

        cur.execute("""
            SELECT COUNT(*) FROM dll_event_notifications
            WHERE owner_uid = %s AND is_read = FALSE
        """, (owner_uid,))

        count = cur.fetchone()[0]
        cur.close()
        dbconnect.close()

        return reply("success", 200, "Unread count", {"count": count})

    except Exception as e:
        return reply("error", 500, f"Error fetching unread count: {str(e)}", "")
