"""
GET /fleet/<client_uid>/summary -- the dashboard's fleet status and geofence
presence in one call.

What it reads, once per request:

  * the units registered to the client (Cassandra unit register);
  * every unit's latest live position, in one Redis MGET of the
    device:location:<imei> snapshots the live feed keeps (the same keys the
    device listings read);
  * for a unit with no usable snapshot, its last heartbeat
    (dll_pulse_status_registry), so a quiet unit still gets a "silent for"
    age -- fired together, as fleet_liveness does;
  * the client's geofences, filtered by the caller's resource grants exactly
    as the geofence list is;
  * today's geofence alerts, for entries and exits.

The arithmetic is in fleet_summary.py. The geofence part can fail on its own:
the fleet status still comes back and `zones` is null with a note.
"""

import json
import logging
from datetime import datetime

import psycopg2.extras
from flask import Blueprint

from . import db_pool, fleet_summary
from .alert_engine import _ring, point_in_ring
from .device_listing import _redis
from .globals import reply, require_auth
from .resources import resource_policy
from .waswa_fleet import FleetUnavailable, _cassandra, _stamp, _units_of

fleet_bp = Blueprint('fleet', __name__)
log = logging.getLogger('fleet')

MGET_CHUNK = 500

# Heartbeat point reads for units the live feed has no snapshot for. A fleet
# with more such units than this gets the rest counted as unread, and says so.
MAX_HEARTBEAT_LOOKUPS = 500


class _LiveStoreDown(Exception):
    pass


def _snapshots(imeis):
    """{imei: snapshot dict}. Raises _LiveStoreDown when Redis cannot be read:
    an unreachable store must not be reported as a fleet with no positions."""
    out = {}
    for start in range(0, len(imeis), MGET_CHUNK):
        chunk = imeis[start:start + MGET_CHUNK]
        try:
            raw = _redis().mget(['device:location:%s' % imei for imei in chunk])
        except Exception as error:      # noqa: BLE001
            raise _LiveStoreDown(str(error)) from error
        for imei, value in zip(chunk, raw):
            if not value:
                continue
            try:
                snapshot = json.loads(value)
            except ValueError:
                continue
            if isinstance(snapshot, dict):
                out[imei] = snapshot
    return out


def _snapshot_seen(snapshot):
    """When the snapshot was written: last_update_epoch, else its local
    date and time. None when neither reads."""
    epoch = snapshot.get('last_update_epoch')
    if epoch:
        try:
            return datetime.fromtimestamp(float(epoch))
        except (TypeError, ValueError, OverflowError, OSError):
            pass
    return _stamp(snapshot.get('local_system_datestamp'),
                  snapshot.get('local_system_timestamp'))


def _heartbeats(imeis):
    """{imei: datetime | 'never' | 'unread'} from the heartbeat registry."""
    out = {imei: 'unread' for imei in imeis}
    if not imeis:
        return out
    try:
        session = _cassandra()
        if session is None:
            return out
        stmt = session.prepare(
            "SELECT last_heartbeat_date, last_heartbeat_time "
            "FROM dll_pulse_status_registry WHERE device_data_imei = ? LIMIT 1")
    except Exception as error:          # noqa: BLE001
        log.warning('fleet summary: heartbeat registry unavailable: %s', error)
        return out

    pending = []
    for imei in imeis:
        try:
            pending.append((imei, session.execute_async(stmt, (imei,))))
        except Exception:               # noqa: BLE001
            pass
    for imei, future in pending:
        try:
            row = future.result().one()
        except Exception:               # noqa: BLE001
            continue
        if row is None:
            out[imei] = 'never'
            continue
        seen = _stamp(getattr(row, 'last_heartbeat_date', None),
                      getattr(row, 'last_heartbeat_time', None))
        if seen is not None:
            out[imei] = seen
    return out


def _readings(units):
    """One fleet_summary reading per unit, plus any notes on what was not
    checked."""
    imeis = [u['imei'] for u in units if u.get('imei')]
    snapshots = _snapshots(imeis)

    readings = {}
    need_heartbeat = []
    for unit in units:
        imei = unit.get('imei')
        if not imei:
            continue
        snapshot = snapshots.get(imei)
        seen = _snapshot_seen(snapshot) if snapshot else None
        readings[imei] = {'imei': imei, 'name': unit.get('name'),
                          'snapshot': snapshot, 'seen': seen, 'unread': False}
        if seen is None:
            need_heartbeat.append(imei)

    notes = []
    looked_up = need_heartbeat[:MAX_HEARTBEAT_LOOKUPS]
    if len(need_heartbeat) > len(looked_up):
        notes.append('%d units have no live position and were not looked up '
                     'in the heartbeat registry; they are counted as unread.'
                     % (len(need_heartbeat) - len(looked_up)))
    beats = _heartbeats(looked_up)
    for imei in need_heartbeat:
        beat = beats.get(imei, 'unread')
        if beat == 'unread':
            readings[imei]['unread'] = True
        elif beat != 'never':
            readings[imei]['seen'] = beat
    return list(readings.values()), notes


def _zones_and_crossings(client_uid):
    """(zones, today's breach types) for the client, as the caller may see
    them."""
    policy = resource_policy()
    connection = db_pool.connect()
    try:
        with connection:
            with connection.cursor(
                    cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                # SELECT *: zones made before migration 043 have no
                # geozone_shape column.
                cursor.execute(
                    "SELECT * FROM dll_geozones "
                    "WHERE geozone_owner = %s OR geozone_uid = ANY(%s)",
                    (str(client_uid), policy.granted_uids('geozone')))
                rows = [dict(r) for r in cursor.fetchall()]
                cursor.execute(
                    "SELECT breach_type FROM dll_event_notifications "
                    "WHERE owner_uid = %s AND COALESCE(geozone_name, '') <> '' "
                    "AND date_triggered >= date_trunc('day', NOW())",
                    (str(client_uid),))
                crossings = [r.get('breach_type') for r in cursor.fetchall()]
    finally:
        connection.close()

    rows = policy.apply('geozone', rows, 'geozone_uid')
    zones = [{'name': r.get('geozone_name') or 'Zone',
              'ring': _ring(r.get('geozone_points')),
              'shape': r.get('geozone_shape') or 'polygon'} for r in rows]
    return zones, crossings


@fleet_bp.route('/fleet/<client_uid>/summary', methods=['GET'])
@require_auth
def fleet_summary_route(client_uid):
    try:
        units = _units_of(str(client_uid))
    except FleetUnavailable as error:
        log.warning('fleet summary: unit register unavailable: %s', error)
        return reply('error', 503,
                     'The unit register is temporarily unavailable, '
                     'please retry', '')

    try:
        readings, notes = _readings(units)
    except _LiveStoreDown as error:
        log.warning('fleet summary: live store unavailable: %s', error)
        return reply('error', 503,
                     'Live positions are temporarily unavailable, '
                     'please retry', '')
    except Exception as error:          # noqa: BLE001
        log.exception('fleet summary failed: %s', error)
        return reply('error', 500, 'Could not build the fleet summary', '')

    now = datetime.now()
    zones = None
    try:
        zone_rows, crossings = _zones_and_crossings(client_uid)
        zones = fleet_summary.zone_presence(
            readings, zone_rows, now, point_in_ring, crossings)
    except Exception as error:          # noqa: BLE001
        log.warning('fleet summary: geofences unavailable: %s', error)
        notes.append('Geofence presence could not be read.')

    return reply('success', 200, 'Fleet summary', {
        'client_uid': str(client_uid),
        'generated_at': now.isoformat(sep=' ', timespec='seconds'),
        'silent_after_minutes': int(
            fleet_summary.SILENT_AFTER.total_seconds() // 60),
        'units_registered': len(units),
        'fleet': fleet_summary.fleet_status(readings, now),
        'zones': zones,
        'notes': notes,
    })
