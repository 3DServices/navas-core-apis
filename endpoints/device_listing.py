"""
Batched, paginated device listings for the CMS gatehouse and ops war room.

The old list endpoints issued ~6 queries and opened a fresh Postgres connection
per device. These helpers read each source once for the whole list, then do the
per-device enrichment only for the requested page.

Pagination is opt-in: without `page` in the payload the full list comes back,
exactly as before, so older clients keep working.
"""

import json
import os
import time

import psycopg2
import redis
from flask import current_app, jsonify

LIVE_ONLINE_TIMEOUT_S = int(os.environ.get("LIVE_ONLINE_TIMEOUT_S", "900"))
MAX_PAGE_SIZE = 200
IN_CHUNK = 100
LIVE_STATUSES = ("Moving", "Parked", "Idling", "Offline")

_redis_client = None


def _redis():
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.Redis(host="127.0.0.1", port=6379, db=0, socket_timeout=2,
                                    socket_connect_timeout=2, decode_responses=True)
    return _redis_client


def page_request(data):
    try:
        page = int(data.get("page") or 0)
    except (TypeError, ValueError):
        page = 0
    try:
        size = int(data.get("page_size") or 25)
    except (TypeError, ValueError):
        size = 25
    size = max(1, min(size, MAX_PAGE_SIZE))
    search = str(data.get("search") or "").strip().lower()
    status = str(data.get("status") or "").strip().capitalize()
    return (page if page > 0 else None), size, search, (status if status in LIVE_STATUSES else "")


def paginate(items, page, size):
    total = len(items)
    if page is None:
        return items, {"page": 1, "page_size": total, "total": total, "total_pages": 1}
    pages = max(1, -(-total // size))
    page = min(page, pages)
    start = (page - 1) * size
    return items[start:start + size], {"page": page, "page_size": size, "total": total, "total_pages": pages}


def paged_reply(message, items, pagination, **extra):
    body = {"status": "success", "message": message, "data": items, "pagination": pagination}
    body.update(extra)
    return jsonify(body), 200


def _chunks(values):
    values = list(values)
    for index in range(0, len(values), IN_CHUNK):
        yield values[index:index + IN_CHUNK]


def cassandra_in(session, cql, keys):
    statement = session.prepare(cql)
    rows = []
    for chunk in _chunks(keys):
        rows.extend(session.execute(statement, (chunk,)))
    return rows


def pg_lookup(sql, keys):
    keys = [k for k in {str(k) for k in keys if k}]
    if not keys:
        return {}
    connection = psycopg2.connect(current_app.config['db_link'])
    try:
        with connection:
            with connection.cursor() as cursor:
                cursor.execute(sql, (keys,))
                return {str(row[0]): row[1:] if len(row) > 2 else row[1] for row in cursor.fetchall()}
    finally:
        connection.close()


def live_snapshots(imeis):
    imeis = list(imeis)
    if not imeis:
        return {}
    try:
        raw = _redis().mget(["device:location:%s" % imei for imei in imeis])
    except Exception:
        return {}
    out = {}
    for imei, value in zip(imeis, raw):
        if not value:
            continue
        try:
            out[imei] = json.loads(value)
        except ValueError:
            continue
    return out


def live_summary(snapshot):
    if not snapshot:
        return {"live_status": "Offline", "device_state": "Offline"}
    if snapshot.get("last_update_epoch"):
        online = time.time() - float(snapshot["last_update_epoch"]) <= LIVE_ONLINE_TIMEOUT_S
    else:
        online = str(snapshot.get("device_state") or "").lower() == "online"
    try:
        speed = float(snapshot.get("speed_log") or 0)
    except (TypeError, ValueError):
        speed = 0.0
    motion = str(snapshot.get("motion_state") or "").lower()
    if not online:
        status = "Offline"
    elif "park" in motion or "stop" in motion:
        status = "Parked"
    elif "idl" in motion:
        status = "Idling"
    elif "mov" in motion or "driv" in motion or speed >= 5:
        status = "Moving"
    elif speed > 0:
        status = "Idling"
    else:
        status = "Parked"
    try:
        latitude = float(snapshot.get("data_latitude"))
        longitude = float(snapshot.get("data_longitude"))
    except (TypeError, ValueError):
        latitude = longitude = None
    return {
        "live_status": status,
        "device_state": "Online" if online else "Offline",
        "motion_state": snapshot.get("motion_state") or "",
        "speed": speed,
        "latitude": latitude,
        "longitude": longitude,
        "geocoded_location": snapshot.get("geocoded_location") or "",
        "last_sync": ("%s %s" % (snapshot.get("local_system_datestamp") or "",
                                 snapshot.get("local_system_timestamp") or "")).strip(),
    }


def matches(search, *values):
    if not search:
        return True
    return any(search in str(value or "").lower() for value in values)
