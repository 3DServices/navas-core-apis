"""
Driver management (migration 052). Rules in driver_rules.py.

Every route works on the signed-in user's own client: a driver of another
client answers 404, as if it did not exist. The access guard has already
checked that any device_imei sent belongs to the caller; assignment checks it
again against the unit register.

  GET  /drivers/registry?status=&q=           the client's drivers, each with
                                              their current unit
  POST /drivers/registry                      {data:{...}} register a driver
  GET  /drivers/registry/<driver_uid>         one driver
  PUT  /drivers/registry/<driver_uid>         {data:{...}} edit (fields sent)
  PUT  /drivers/registry/<driver_uid>/status  {data:{status, reason}}
  POST /drivers/registry/<driver_uid>/assign  {data:{device_imei}}
  POST /drivers/registry/<driver_uid>/unassign
  GET  /drivers/registry/<driver_uid>/assignments   history, newest first
  GET  /drivers/registry/unit/<device_imei>   the unit's current driver
  POST /drivers/registry/<driver_uid>/photo   multipart "photo"
  GET  /drivers/registry/<driver_uid>/photo   the photo, to signed-in users
                                              of the same client only
"""

import logging
import os
import uuid
from contextlib import contextmanager
from datetime import datetime
from zoneinfo import ZoneInfo

import psycopg2.errors
import psycopg2.extras
from flask import Blueprint, g, request, send_file

from . import db_pool, driver_rules as rules
from .globals import log_audit_event, reply, require_auth, resolve_client_account

driver_registry_bp = Blueprint('driver_registry', __name__)
log = logging.getLogger('drivers')

KAMPALA = ZoneInfo('Africa/Kampala')
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Not under a public route: photos are sent only by GET .../photo, which checks
# the caller's client.
PHOTO_DIR = os.path.join(_PROJECT_ROOT, 'uploads', 'drivers')

_NO_CLIENT = 'Drivers belong to a client account.'
_NOT_FOUND = 'Driver not found.'
_COLUMNS = (
    'driver_uid, full_name, phone, permit_number, permit_expiry, '
    'permit_classes, ibutton_id, national_id, employee_number, photo_file, '
    'emergency_name, emergency_phone, home_branch, notes, status, '
    'status_reason, created_at')


def _today():
    return datetime.now(KAMPALA).date()


@contextmanager
def _cursor():
    connection = db_pool.connect()
    try:
        with connection:
            with connection.cursor(
                    cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                yield cursor
    finally:
        connection.close()


def _client(cursor):
    return resolve_client_account(cursor, g.current_user['account_uid'])


def _actor():
    return g.current_user['account_uid']


def _audit(action, obj, client, meta=None):
    try:
        log_audit_event(actor=_actor(), action=action, obj=obj,
                        domain='DRIVERS', tenant_id=client, meta=meta)
    except Exception:                   # noqa: BLE001 -- never fail the change
        log.exception('driver audit failed')


def _body():
    payload = request.get_json(silent=True) or {}
    data = payload.get('data', payload)
    return data if isinstance(data, dict) else {}


def _driver(cursor, client, driver_uid, lock=False):
    """One of the client's drivers, with their current unit, or None."""
    cursor.execute(
        f"""SELECT d.{_COLUMNS.replace(', ', ', d.')},
                   a.device_imei AS current_imei, a.assigned_at
              FROM dll_drivers d
              LEFT JOIN dll_driver_assignments a
                ON a.driver_uid = d.driver_uid AND a.ended_at IS NULL
             WHERE d.driver_uid = %s AND d.client_uid = %s
             {'FOR UPDATE OF d' if lock else ''}""",
        (driver_uid, client))
    return cursor.fetchone()


def _duplicate(error):
    """(field, message) for a unique-index clash, or None."""
    name = getattr(getattr(error, 'diag', None), 'constraint_name', '') or ''
    return rules.DUPLICATE_FIELDS.get(name)


def _invalid(errors):
    first = next(iter(errors.values()))
    return reply('error', 400, first, {'errors': errors})


def _end_open(cursor, where, value, reason):
    cursor.execute(
        f"""UPDATE dll_driver_assignments
               SET ended_at = NOW(), ended_by = %s, end_reason = %s
             WHERE {where} = %s AND ended_at IS NULL""",
        (_actor(), reason, value))


# ── list / register ──────────────────────────────────────────────────────────

@driver_registry_bp.route('/drivers/registry', methods=['GET'])
@require_auth
def list_drivers():
    status = (request.args.get('status') or '').strip().lower()
    query = (request.args.get('q') or '').strip()
    try:
        with _cursor() as cur:
            client = _client(cur)
            if not client:
                return reply('error', 403, _NO_CLIENT, '')
            sql = f"""SELECT d.{_COLUMNS.replace(', ', ', d.')},
                             a.device_imei AS current_imei, a.assigned_at
                        FROM dll_drivers d
                        LEFT JOIN dll_driver_assignments a
                          ON a.driver_uid = d.driver_uid AND a.ended_at IS NULL
                       WHERE d.client_uid = %s"""
            args = [client]
            if status in rules.STATUSES:
                sql += " AND d.status = %s"
                args.append(status)
            if query:
                like = '%' + query.lower() + '%'
                sql += """ AND (LOWER(d.full_name) LIKE %s OR d.phone LIKE %s
                               OR LOWER(d.permit_number) LIKE %s
                               OR LOWER(COALESCE(d.employee_number, '')) LIKE %s)"""
                args += [like, '%' + query + '%', like, like]
            sql += " ORDER BY LOWER(d.full_name)"
            cur.execute(sql, args)
            today = _today()
            drivers = [rules.public(r, today) for r in cur.fetchall()]
        return reply('success', 200, 'Drivers', drivers)
    except Exception:                   # noqa: BLE001
        log.exception('drivers list failed')
        return reply('error', 500, 'Could not load drivers.', '')


@driver_registry_bp.route('/drivers/registry', methods=['POST'])
@require_auth
def register_driver():
    clean, errors = rules.validate(_body())
    if errors:
        return _invalid(errors)
    driver_uid = str(uuid.uuid4())
    try:
        with _cursor() as cur:
            client = _client(cur)
            if not client:
                return reply('error', 403, _NO_CLIENT, '')
            fields = dict(clean, driver_uid=driver_uid, client_uid=client,
                          created_by=_actor())
            cur.execute(
                f"INSERT INTO dll_drivers ({', '.join(fields)}) "
                f"VALUES ({', '.join(['%s'] * len(fields))})",
                list(fields.values()))
            driver = rules.public(_driver(cur, client, driver_uid), _today())
        _audit('DRIVER_REGISTER', driver_uid, client,
               {'full_name': clean['full_name']})
        return reply('success', 201, 'Driver registered', driver)
    except psycopg2.errors.UniqueViolation as error:
        dup = _duplicate(error)
        if dup:
            return reply('error', 409, dup[1], {'errors': {dup[0]: dup[1]}})
        return reply('error', 409, 'This driver is already registered.', '')
    except Exception:                   # noqa: BLE001
        log.exception('driver register failed')
        return reply('error', 500, 'Could not register the driver.', '')


# ── one driver ───────────────────────────────────────────────────────────────

@driver_registry_bp.route('/drivers/registry/<driver_uid>', methods=['GET'])
@require_auth
def get_driver(driver_uid):
    try:
        with _cursor() as cur:
            client = _client(cur)
            if not client:
                return reply('error', 403, _NO_CLIENT, '')
            row = _driver(cur, client, driver_uid)
        if not row:
            return reply('error', 404, _NOT_FOUND, '')
        return reply('success', 200, 'Driver', rules.public(row, _today()))
    except Exception:                   # noqa: BLE001
        log.exception('driver get failed')
        return reply('error', 500, 'Could not load the driver.', '')


@driver_registry_bp.route('/drivers/registry/<driver_uid>', methods=['PUT'])
@require_auth
def edit_driver(driver_uid):
    clean, errors = rules.validate(_body(), partial=True)
    if errors:
        return _invalid(errors)
    if not clean:
        return reply('error', 400, 'Nothing to change.', '')
    try:
        with _cursor() as cur:
            client = _client(cur)
            if not client:
                return reply('error', 403, _NO_CLIENT, '')
            if not _driver(cur, client, driver_uid, lock=True):
                return reply('error', 404, _NOT_FOUND, '')
            sets = ', '.join(f'{k} = %s' for k in clean)
            cur.execute(
                f"UPDATE dll_drivers SET {sets}, updated_at = NOW() "
                "WHERE driver_uid = %s AND client_uid = %s",
                list(clean.values()) + [driver_uid, client])
            driver = rules.public(_driver(cur, client, driver_uid), _today())
        _audit('DRIVER_EDIT', driver_uid, client, {'fields': sorted(clean)})
        return reply('success', 200, 'Driver updated', driver)
    except psycopg2.errors.UniqueViolation as error:
        dup = _duplicate(error)
        if dup:
            return reply('error', 409, dup[1], {'errors': {dup[0]: dup[1]}})
        return reply('error', 409, 'Another driver already has these details.', '')
    except Exception:                   # noqa: BLE001
        log.exception('driver edit failed')
        return reply('error', 500, 'Could not update the driver.', '')


@driver_registry_bp.route('/drivers/registry/<driver_uid>/status', methods=['PUT'])
@require_auth
def change_status(driver_uid):
    data = _body()
    wanted = str(data.get('status') or '').strip().lower()
    reason = str(data.get('reason') or '').strip()[:500] or None
    try:
        with _cursor() as cur:
            client = _client(cur)
            if not client:
                return reply('error', 403, _NO_CLIENT, '')
            row = _driver(cur, client, driver_uid, lock=True)
            if not row:
                return reply('error', 404, _NOT_FOUND, '')
            refusal = rules.status_change_refusal(row['status'], wanted)
            if refusal:
                return reply('error', 400, refusal, '')
            cur.execute(
                "UPDATE dll_drivers SET status = %s, status_reason = %s, "
                "updated_at = NOW() WHERE driver_uid = %s AND client_uid = %s",
                (wanted, reason, driver_uid, client))
            if rules.ends_assignment(wanted):
                _end_open(cur, 'driver_uid', driver_uid, wanted)
            driver = rules.public(_driver(cur, client, driver_uid), _today())
        _audit('DRIVER_STATUS', driver_uid, client,
               {'from': row['status'], 'to': wanted, 'reason': reason})
        return reply('success', 200, f'Driver {wanted}', driver)
    except Exception:                   # noqa: BLE001
        log.exception('driver status failed')
        return reply('error', 500, "Could not change the driver's status.", '')


# ── assignment ───────────────────────────────────────────────────────────────

def _unit_client(imei):
    """The client a unit is registered to, from the Cassandra register."""
    from .access_guard import device_client_lookup
    return device_client_lookup(imei)


@driver_registry_bp.route('/drivers/registry/<driver_uid>/assign', methods=['POST'])
@require_auth
def assign(driver_uid):
    imei = str(_body().get('device_imei') or '').strip()
    if not imei:
        return reply('error', 400, 'Choose a vehicle.', '')
    try:
        owner = _unit_client(imei)
    except Exception:                   # noqa: BLE001 -- register unreachable
        return reply('error', 503,
                     "We couldn't check this vehicle right now. Please try again.", '')
    try:
        with _cursor() as cur:
            client = _client(cur)
            if not client:
                return reply('error', 403, _NO_CLIENT, '')
            if owner != client:
                return reply('error', 403,
                             "This vehicle doesn't belong to your account.", '')
            row = _driver(cur, client, driver_uid, lock=True)
            if not row:
                return reply('error', 404, _NOT_FOUND, '')
            refusal = rules.assignment_refusal(
                row['status'], row['permit_expiry'], _today())
            if refusal:
                return reply('error', 400, refusal, '')
            if row['current_imei'] == imei:
                return reply('success', 200, 'Already assigned',
                             rules.public(row, _today()))
            # One unit per driver, one driver per unit: end both, then start.
            _end_open(cur, 'driver_uid', driver_uid, 'reassigned')
            _end_open(cur, 'device_imei', imei, 'replaced')
            cur.execute(
                """INSERT INTO dll_driver_assignments
                       (driver_uid, device_imei, client_uid, assigned_by)
                   VALUES (%s, %s, %s, %s)""",
                (driver_uid, imei, client, _actor()))
            driver = rules.public(_driver(cur, client, driver_uid), _today())
        _audit('DRIVER_ASSIGN', driver_uid, client, {'device_imei': imei})
        return reply('success', 200, 'Driver assigned', driver)
    except psycopg2.errors.UniqueViolation:
        # Someone assigned the same driver or unit in the same moment.
        return reply('error', 409,
                     'This assignment just changed. Refresh and try again.', '')
    except Exception:                   # noqa: BLE001
        log.exception('driver assign failed')
        return reply('error', 500, 'Could not assign the driver.', '')


@driver_registry_bp.route('/drivers/registry/<driver_uid>/unassign', methods=['POST'])
@require_auth
def unassign(driver_uid):
    try:
        with _cursor() as cur:
            client = _client(cur)
            if not client:
                return reply('error', 403, _NO_CLIENT, '')
            row = _driver(cur, client, driver_uid, lock=True)
            if not row:
                return reply('error', 404, _NOT_FOUND, '')
            if not row['current_imei']:
                return reply('error', 400, 'This driver has no vehicle.', '')
            _end_open(cur, 'driver_uid', driver_uid, 'unassigned')
            driver = rules.public(_driver(cur, client, driver_uid), _today())
        _audit('DRIVER_UNASSIGN', driver_uid, client,
               {'device_imei': row['current_imei']})
        return reply('success', 200, 'Driver unassigned', driver)
    except Exception:                   # noqa: BLE001
        log.exception('driver unassign failed')
        return reply('error', 500, 'Could not unassign the driver.', '')


@driver_registry_bp.route('/drivers/registry/<driver_uid>/assignments', methods=['GET'])
@require_auth
def assignment_history(driver_uid):
    try:
        with _cursor() as cur:
            client = _client(cur)
            if not client:
                return reply('error', 403, _NO_CLIENT, '')
            if not _driver(cur, client, driver_uid):
                return reply('error', 404, _NOT_FOUND, '')
            cur.execute(
                """SELECT device_imei, assigned_at, ended_at, end_reason
                     FROM dll_driver_assignments
                    WHERE driver_uid = %s AND client_uid = %s
                    ORDER BY assigned_at DESC LIMIT 200""",
                (driver_uid, client))
            history = [{
                'device_imei': r['device_imei'],
                'assigned_at': r['assigned_at'].isoformat(),
                'ended_at': r['ended_at'].isoformat() if r['ended_at'] else None,
                'end_reason': r['end_reason'],
            } for r in cur.fetchall()]
        return reply('success', 200, 'Assignments', history)
    except Exception:                   # noqa: BLE001
        log.exception('driver history failed')
        return reply('error', 500, 'Could not load the history.', '')


@driver_registry_bp.route('/drivers/registry/unit/<device_imei>', methods=['GET'])
@require_auth
def unit_driver(device_imei):
    """The unit's current driver, or data null when it has none."""
    try:
        with _cursor() as cur:
            client = _client(cur)
            if not client:
                return reply('error', 403, _NO_CLIENT, '')
            cur.execute(
                """SELECT driver_uid FROM dll_driver_assignments
                    WHERE device_imei = %s AND client_uid = %s
                      AND ended_at IS NULL""",
                (device_imei, client))
            found = cur.fetchone()
            row = _driver(cur, client, found['driver_uid']) if found else None
        return reply('success', 200, 'Unit driver',
                     rules.public(row, _today()) if row else None)
    except Exception:                   # noqa: BLE001
        log.exception('unit driver failed')
        return reply('error', 500, "Could not load the vehicle's driver.", '')


# ── photo ────────────────────────────────────────────────────────────────────

@driver_registry_bp.route('/drivers/registry/<driver_uid>/photo', methods=['POST'])
@require_auth
def upload_photo(driver_uid):
    upload = request.files.get('photo')
    if upload is None:
        return reply('error', 400, "Send the image in a 'photo' field.", '')
    data = upload.read(rules.PHOTO_MAX_BYTES + 1)
    if len(data) > rules.PHOTO_MAX_BYTES:
        return reply('error', 400, 'The photo must be 5 MB or less.', '')
    kind = rules.photo_type(data)
    if kind is None:
        return reply('error', 400, 'The photo must be a JPEG, PNG or WebP image.', '')
    try:
        with _cursor() as cur:
            client = _client(cur)
            if not client:
                return reply('error', 403, _NO_CLIENT, '')
            row = _driver(cur, client, driver_uid, lock=True)
            if not row:
                return reply('error', 404, _NOT_FOUND, '')
            os.makedirs(PHOTO_DIR, exist_ok=True)
            name = f'{driver_uid}_{uuid.uuid4().hex[:12]}.{kind}'
            with open(os.path.join(PHOTO_DIR, name), 'wb') as handle:
                handle.write(data)
            cur.execute(
                "UPDATE dll_drivers SET photo_file = %s, updated_at = NOW() "
                "WHERE driver_uid = %s AND client_uid = %s",
                (name, driver_uid, client))
            old = row['photo_file']
            driver = rules.public(_driver(cur, client, driver_uid), _today())
        if old and old != name:
            try:
                os.remove(os.path.join(PHOTO_DIR, os.path.basename(old)))
            except OSError:
                pass
        _audit('DRIVER_PHOTO', driver_uid, client)
        return reply('success', 200, 'Photo saved', driver)
    except Exception:                   # noqa: BLE001
        log.exception('driver photo upload failed')
        return reply('error', 500, 'Could not save the photo.', '')


@driver_registry_bp.route('/drivers/registry/<driver_uid>/photo', methods=['GET'])
@require_auth
def get_photo(driver_uid):
    try:
        with _cursor() as cur:
            client = _client(cur)
            if not client:
                return reply('error', 403, _NO_CLIENT, '')
            row = _driver(cur, client, driver_uid)
        if not row or not row['photo_file']:
            return reply('error', 404, 'No photo.', '')
        name = os.path.basename(row['photo_file'])
        path = os.path.join(PHOTO_DIR, name)
        if not os.path.isfile(path):
            return reply('error', 404, 'No photo.', '')
        kind = name.rsplit('.', 1)[-1]
        response = send_file(path, mimetype=rules.PHOTO_MIME.get(kind, 'image/jpeg'))
        # Personal data: the phone may cache it, shared caches may not.
        response.headers['Cache-Control'] = 'private, max-age=3600'
        return response
    except Exception:                   # noqa: BLE001
        log.exception('driver photo get failed')
        return reply('error', 500, 'Could not load the photo.', '')
