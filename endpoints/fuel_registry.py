"""
FuelMath: fuel issued to drivers (migration 053). Rules in fuel_rules.py.

Every route works on the signed-in user's own client: an issue of another
client answers 404, as if it did not exist. The access guard has already
checked that any device_imei sent belongs to the caller; recording an issue
and setting a profile check it again against the unit register.

  GET  /fuel/profiles                       the client's vehicle fuel profiles
  GET  /fuel/capabilities                   per vehicle: has_profile, and
                                            fuel_sensor none | needs_calibration
                                            | ready
  GET  /fuel/profiles/<device_imei>         one (data null when none is set)
  PUT  /fuel/profiles/<device_imei>         {data:{fuel_type, tank_capacity_l,
                                            baseline_km_per_l, tolerance_pct}}
  GET  /fuel/issues?device_imei=&driver_uid=&from=&to=&review=&voided=&limit=
                                            newest first
  POST /fuel/issues                         {data:{...}} record an issue; it is
                                            checked against the tracker here
  GET  /fuel/issues/<issue_uid>             one issue
  POST /fuel/issues/<issue_uid>/review      {data:{outcome, note}}
  POST /fuel/issues/<issue_uid>/void        {data:{reason}}
  POST /fuel/issues/<issue_uid>/receipt     multipart "photo"
  GET  /fuel/issues/<issue_uid>/receipt     the photo, same client only
  GET  /fuel/summary?from=&to=              totals per vehicle and driver
  POST /data-stream/reports/fuel/<kind>/generate-data
                                            issuance, consumption or exceptions
                                            report rows (fuel_report.py)
  GET  /fuel/stations                       station names used before, for
                                            the app's suggestions
"""

import logging
import os
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import psycopg2.errors
import psycopg2.extras
from flask import Blueprint, g, request, send_file

from . import db_pool, driver_rules, fuel_rules as rules, location_store
from .globals import log_audit_event, reply, require_auth, resolve_client_account

fuel_registry_bp = Blueprint('fuel_registry', __name__)
log = logging.getLogger('fuel')

KAMPALA = ZoneInfo('Africa/Kampala')
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Not under a public route: receipts are sent only by GET .../receipt, which
# checks the caller's client.
RECEIPT_DIR = os.path.join(_PROJECT_ROOT, 'uploads', 'fuel_receipts')

_NO_CLIENT = 'Fuel records belong to a client account.'
_NOT_FOUND = 'Fuel issue not found.'
_NOT_YOURS = "This vehicle doesn't belong to your account."
_UNIT_UNREACHABLE = "We couldn't check this vehicle right now. Please try again."
_ISSUE_SELECT = """SELECT f.*, d.full_name AS driver_name
                     FROM dll_fuel_issues f
                     LEFT JOIN dll_drivers d ON d.driver_uid = f.driver_uid"""
_PROFILE_COLUMNS = ('device_imei, fuel_type, tank_capacity_l, baseline_km_per_l, '
                    'tolerance_pct, updated_at')


def _now():
    """Local (EAT) time, naive: issued_at is stored the same way."""
    return datetime.now(KAMPALA).replace(tzinfo=None)


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
                        domain='FUEL', tenant_id=client, meta=meta)
    except Exception:                   # noqa: BLE001 -- never fail the change
        log.exception('fuel audit failed')


def _body():
    payload = request.get_json(silent=True) or {}
    data = payload.get('data', payload)
    return data if isinstance(data, dict) else {}


def _invalid(errors):
    first = next(iter(errors.values()))
    return reply('error', 400, first, {'errors': errors})


def _unit_client(imei):
    """The client a unit is registered to, from the Cassandra register."""
    from .access_guard import device_client_lookup
    return device_client_lookup(imei)


def _issue(cursor, client, issue_uid, lock=False):
    cursor.execute(
        f"""{_ISSUE_SELECT}
             WHERE f.issue_uid = %s AND f.client_uid = %s
             {'FOR UPDATE OF f' if lock else ''}""",
        (issue_uid, client))
    return cursor.fetchone()


def _profile(cursor, client, imei):
    cursor.execute(
        f"SELECT {_PROFILE_COLUMNS} FROM dll_fuel_vehicle_profiles "
        "WHERE device_imei = %s AND client_uid = %s", (imei, client))
    return cursor.fetchone()


def _day(value, default):
    parsed = driver_rules.parse_date(value) if value else None
    return parsed or default


# ── profiles ─────────────────────────────────────────────────────────────────

@fuel_registry_bp.route('/fuel/profiles', methods=['GET'])
@require_auth
def list_profiles():
    try:
        with _cursor() as cur:
            client = _client(cur)
            if not client:
                return reply('error', 403, _NO_CLIENT, '')
            cur.execute(
                f"SELECT {_PROFILE_COLUMNS} FROM dll_fuel_vehicle_profiles "
                "WHERE client_uid = %s ORDER BY device_imei", (client,))
            profiles = [rules.public_profile(r) for r in cur.fetchall()]
        return reply('success', 200, 'Fuel profiles', profiles)
    except Exception:                   # noqa: BLE001
        log.exception('fuel profiles list failed')
        return reply('error', 500, 'Could not load the fuel profiles.', '')


def _sensor_sources(session, imeis):
    """{imei: the 'fuel_level' config's data source, or None}, read
    concurrently: one point read per unit."""
    from cassandra.concurrent import execute_concurrent_with_args
    stmt = session.prepare(
        "SELECT config_param_data_source_uid FROM dll_device_local_configs "
        "WHERE config_parameter = ? AND local_device_imei = ? ALLOW FILTERING")
    outcomes = execute_concurrent_with_args(
        session, stmt, [('fuel_level', imei) for imei in imeis],
        concurrency=16, raise_on_first_error=True)
    sources = {}
    for imei, (ok, result) in zip(imeis, outcomes):
        rows = list(result) if ok else []
        # Two configs for one parameter is ambiguous; data.py treats it as
        # none, and so does this.
        sources[imei] = (getattr(rows[0], 'config_param_data_source_uid', None)
                         if len(rows) == 1 else None)
    return sources


@fuel_registry_bp.route('/fuel/capabilities', methods=['GET'])
@require_auth
def capabilities():
    """What fuel features each of the client's vehicles can use:
    [{device_imei, name, has_profile, fuel_sensor}] where fuel_sensor is
    'none', 'needs_calibration' or 'ready' (fuel_rules.sensor_state)."""
    try:
        with _cursor() as cur:
            client = _client(cur)
            if not client:
                return reply('error', 403, _NO_CLIENT, '')
            cur.execute("SELECT device_imei FROM dll_fuel_vehicle_profiles "
                        "WHERE client_uid = %s", (client,))
            profiled = {r['device_imei'] for r in cur.fetchall()}

            from .devices import get_cassandra_session
            session = get_cassandra_session()
            if session is None:
                return reply('error', 503, _UNIT_UNREACHABLE, '')
            stmt = session.prepare(
                "SELECT device_imei, device_name FROM dll_device_basic_data "
                "WHERE device_client = ? ALLOW FILTERING")
            units = [(str(r.device_imei), r.device_name or str(r.device_imei))
                     for r in session.execute(stmt, (client,))]
            imeis = [imei for imei, _ in units]
            sources = _sensor_sources(session, imeis) if imeis else {}

            cur.execute("SELECT DISTINCT device_imei FROM dll_calibrated_fuel_data "
                        "WHERE device_imei = ANY(%s)", (imeis,))
            calibrated = {r['device_imei'] for r in cur.fetchall()}
        return reply('success', 200, 'Fuel capabilities', sorted((
            {'device_imei': imei, 'name': name, 'has_profile': imei in profiled,
             'fuel_sensor': rules.sensor_state(sources.get(imei), imei in calibrated)}
            for imei, name in units), key=lambda u: u['name'].lower()))
    except Exception:                   # noqa: BLE001
        log.exception('fuel capabilities failed')
        return reply('error', 500, 'Could not load the fuel capabilities.', '')


@fuel_registry_bp.route('/fuel/profiles/<device_imei>', methods=['GET'])
@require_auth
def get_profile(device_imei):
    try:
        with _cursor() as cur:
            client = _client(cur)
            if not client:
                return reply('error', 403, _NO_CLIENT, '')
            row = _profile(cur, client, device_imei)
        return reply('success', 200, 'Fuel profile',
                     rules.public_profile(row) if row else None)
    except Exception:                   # noqa: BLE001
        log.exception('fuel profile get failed')
        return reply('error', 500, 'Could not load the fuel profile.', '')


@fuel_registry_bp.route('/fuel/profiles/<device_imei>', methods=['PUT'])
@require_auth
def set_profile(device_imei):
    clean, errors = rules.validate_profile(_body())
    if errors:
        return _invalid(errors)
    try:
        owner = _unit_client(device_imei)
    except Exception:                   # noqa: BLE001 -- register unreachable
        return reply('error', 503, _UNIT_UNREACHABLE, '')
    try:
        with _cursor() as cur:
            client = _client(cur)
            if not client:
                return reply('error', 403, _NO_CLIENT, '')
            if owner != client:
                return reply('error', 403, _NOT_YOURS, '')
            cur.execute(
                """INSERT INTO dll_fuel_vehicle_profiles
                       (device_imei, client_uid, fuel_type, tank_capacity_l,
                        baseline_km_per_l, tolerance_pct, updated_by)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (device_imei) DO UPDATE SET
                       client_uid = EXCLUDED.client_uid,
                       fuel_type = EXCLUDED.fuel_type,
                       tank_capacity_l = EXCLUDED.tank_capacity_l,
                       baseline_km_per_l = EXCLUDED.baseline_km_per_l,
                       tolerance_pct = EXCLUDED.tolerance_pct,
                       updated_by = EXCLUDED.updated_by,
                       updated_at = NOW()""",
                (device_imei, client, clean['fuel_type'], clean['tank_capacity_l'],
                 clean['baseline_km_per_l'], clean['tolerance_pct'], _actor()))
            profile = rules.public_profile(_profile(cur, client, device_imei))
        _audit('FUEL_PROFILE', device_imei, client, clean)
        return reply('success', 200, 'Fuel profile saved', profile)
    except Exception:                   # noqa: BLE001
        log.exception('fuel profile set failed')
        return reply('error', 500, 'Could not save the fuel profile.', '')


# ── issues ───────────────────────────────────────────────────────────────────

@fuel_registry_bp.route('/fuel/issues', methods=['GET'])
@require_auth
def list_issues():
    args = request.args
    review = (args.get('review') or '').strip().lower()
    try:
        limit = max(1, min(1000, int(args.get('limit') or 200)))
    except ValueError:
        limit = 200
    try:
        with _cursor() as cur:
            client = _client(cur)
            if not client:
                return reply('error', 403, _NO_CLIENT, '')
            sql = _ISSUE_SELECT + " WHERE f.client_uid = %s"
            params = [client]
            if args.get('device_imei'):
                sql += " AND f.device_imei = %s"
                params.append(args['device_imei'].strip())
            if args.get('driver_uid'):
                sql += " AND f.driver_uid = %s"
                params.append(args['driver_uid'].strip())
            start = driver_rules.parse_date(args.get('from')) if args.get('from') else None
            end = driver_rules.parse_date(args.get('to')) if args.get('to') else None
            if start:
                sql += " AND f.issued_at >= %s"
                params.append(datetime.combine(start, datetime.min.time()))
            if end:
                sql += " AND f.issued_at < %s"
                params.append(datetime.combine(end + timedelta(days=1),
                                               datetime.min.time()))
            if review in ('open', 'explained', 'confirmed_loss'):
                sql += " AND f.review_state = %s"
                params.append(review)
            elif review == 'reviewed':
                sql += " AND f.review_state IN ('explained', 'confirmed_loss')"
            if (args.get('voided') or '').lower() != 'include':
                sql += " AND f.voided_at IS NULL"
            sql += " ORDER BY f.issued_at DESC LIMIT %s"
            params.append(limit)
            cur.execute(sql, params)
            issues = [rules.public_issue(r) for r in cur.fetchall()]
        return reply('success', 200, 'Fuel issues', issues)
    except Exception:                   # noqa: BLE001
        log.exception('fuel issues list failed')
        return reply('error', 500, 'Could not load the fuel issues.', '')


def _read_points(imei, start, end):
    """Tracker fixes between two local datetimes, oldest first, or None when
    the position store could not be read."""
    try:
        from .devices import get_cassandra_session
        rows, _ = location_store.fixes(
            get_cassandra_session(), imei, start.date(), end.date(),
            datetime_from=start, datetime_to=end,
            dedupe_coordinates=False, newest_first=False)
    except Exception:                   # noqa: BLE001 -- PositionsUnavailable too
        log.warning('fuel: positions for %s unavailable', imei, exc_info=True)
        return None
    return [{'lat': r['lat'], 'lon': r['lon'], 'at': r['at'], 'place': r.get('place')}
            for r in rows if r.get('at') is not None]


def _context(cur, client, clean):
    """What assess() needs from the database, for the issue being recorded."""
    imei, at = clean['device_imei'], clean['issued_at']
    cur.execute(
        """SELECT issue_uid, issued_at FROM dll_fuel_issues
            WHERE device_imei = %s AND client_uid = %s AND voided_at IS NULL
              AND full_tank AND issued_at < %s
            ORDER BY issued_at DESC LIMIT 1""", (imei, client, at))
    previous_full = cur.fetchone()

    since_full = []
    if previous_full:
        cur.execute(
            """SELECT litres FROM dll_fuel_issues
                WHERE device_imei = %s AND client_uid = %s AND voided_at IS NULL
                  AND issued_at > %s AND issued_at < %s""",
            (imei, client, previous_full['issued_at'], at))
        since_full = cur.fetchall()

    cur.execute(
        """SELECT issued_at, odometer_km FROM dll_fuel_issues
            WHERE device_imei = %s AND client_uid = %s AND voided_at IS NULL
              AND odometer_km IS NOT NULL AND issued_at < %s
            ORDER BY issued_at DESC LIMIT 1""", (imei, client, at))
    previous_odometer = cur.fetchone()

    cur.execute(
        """SELECT driver_uid FROM dll_driver_assignments
            WHERE device_imei = %s AND client_uid = %s AND assigned_at <= %s
              AND (ended_at IS NULL OR ended_at > %s)
            ORDER BY assigned_at DESC LIMIT 1""", (imei, client, at, at))
    assigned = cur.fetchone()

    cur.execute(
        """SELECT COUNT(*) AS n FROM dll_fuel_issues
            WHERE device_imei = %s AND client_uid = %s AND voided_at IS NULL
              AND issued_at BETWEEN %s AND %s""",
        (imei, client, at - rules.DUPLICATE_WINDOW, at + rules.DUPLICATE_WINDOW))
    nearby = cur.fetchone()['n']

    # Positions: from the previous full tank (when it is close enough to
    # measure) or the previous odometer reading, to just after the issue.
    start = at - rules.READ_MARGIN
    for earlier in (previous_full, previous_odometer):
        if earlier and at - earlier['issued_at'] <= rules.FILL_SPAN_MAX:
            start = min(start, earlier['issued_at'])
    points = _read_points(imei, start, at + rules.READ_MARGIN)

    return dict(previous_full=previous_full, since_full=since_full,
                previous_odometer=previous_odometer, points=points,
                assigned_driver_uid=assigned['driver_uid'] if assigned else None,
                nearby_issues=nearby)


def _send_alerts(cur, issue, profile):
    """Event-rule alerts for a new issue (fuel_issue_flagged,
    high_fuel_consumption). A failure here is logged and the issue is still
    recorded: losing a receipt over an SMS would be the wrong way round."""
    cur.execute("SAVEPOINT fuel_alerts")
    try:
        from .alert_engine import fuel_issue_alerts
        fuel_issue_alerts(cur, issue, profile)
        cur.execute("RELEASE SAVEPOINT fuel_alerts")
    except Exception:                   # noqa: BLE001
        cur.execute("ROLLBACK TO SAVEPOINT fuel_alerts")
        log.warning('fuel: alerts for %s failed', issue.get('issue_uid'), exc_info=True)


@fuel_registry_bp.route('/fuel/issues', methods=['POST'])
@require_auth
def record_issue():
    data = _body()
    imei = ''.join(str(data.get('device_imei') or '').split())
    if not imei:
        return _invalid({'device_imei': 'Choose a vehicle.'})
    try:
        owner = _unit_client(imei)
    except Exception:                   # noqa: BLE001 -- register unreachable
        return reply('error', 503, _UNIT_UNREACHABLE, '')
    issue_uid = str(uuid.uuid4())
    try:
        with _cursor() as cur:
            client = _client(cur)
            if not client:
                return reply('error', 403, _NO_CLIENT, '')
            if owner != client:
                return reply('error', 403, _NOT_YOURS, '')
            # One issue per vehicle at a time: two recorded at once would
            # each miss the other in the fill-to-fill sums.
            cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))",
                        ('fuel:' + imei,))
            profile = _profile(cur, client, imei)
            clean, errors = rules.validate_issue(
                data, _now(), profile['fuel_type'] if profile else None)
            if errors:
                return _invalid(errors)
            cur.execute(
                """SELECT driver_uid, status, permit_expiry FROM dll_drivers
                    WHERE driver_uid = %s AND client_uid = %s""",
                (clean['driver_uid'], client))
            driver = cur.fetchone()
            if not driver:
                return _invalid({'driver_uid': 'Choose one of your drivers.'})

            result = rules.assess(clean, profile=profile, driver=driver,
                                  **_context(cur, client, clean))
            fields = dict(clean, **result, issue_uid=issue_uid, client_uid=client,
                          issued_by=_actor())
            fields['flags'] = ','.join(result['flags'])
            cur.execute(
                f"INSERT INTO dll_fuel_issues ({', '.join(fields)}) "
                f"VALUES ({', '.join(['%s'] * len(fields))})",
                list(fields.values()))
            issue = rules.public_issue(_issue(cur, client, issue_uid))
            _send_alerts(cur, issue, profile)
        _audit('FUEL_ISSUE', issue_uid, client,
               {'device_imei': imei, 'litres': clean['litres'],
                'total_cost': clean['total_cost'], 'flags': result['flags']})
        return reply('success', 201, 'Fuel issue recorded', issue)
    except psycopg2.errors.UniqueViolation as error:
        name = getattr(getattr(error, 'diag', None), 'constraint_name', '') or ''
        field, message = rules.DUPLICATE_FIELDS.get(
            name, ('receipt_number', 'This issue is already recorded.'))
        return reply('error', 409, message, {'errors': {field: message}})
    except Exception:                   # noqa: BLE001
        log.exception('fuel issue record failed')
        return reply('error', 500, 'Could not record the fuel issue.', '')


@fuel_registry_bp.route('/fuel/issues/<issue_uid>', methods=['GET'])
@require_auth
def get_issue(issue_uid):
    try:
        with _cursor() as cur:
            client = _client(cur)
            if not client:
                return reply('error', 403, _NO_CLIENT, '')
            row = _issue(cur, client, issue_uid)
        if not row:
            return reply('error', 404, _NOT_FOUND, '')
        return reply('success', 200, 'Fuel issue', rules.public_issue(row))
    except Exception:                   # noqa: BLE001
        log.exception('fuel issue get failed')
        return reply('error', 500, 'Could not load the fuel issue.', '')


@fuel_registry_bp.route('/fuel/issues/<issue_uid>/review', methods=['POST'])
@require_auth
def review_issue(issue_uid):
    data = _body()
    outcome = str(data.get('outcome') or '').strip().lower()
    note = str(data.get('note') or '').strip()[:rules.NOTES_MAX]
    if len(note) < 3:
        return _invalid({'note': 'Say what was found.'})
    try:
        with _cursor() as cur:
            client = _client(cur)
            if not client:
                return reply('error', 403, _NO_CLIENT, '')
            row = _issue(cur, client, issue_uid, lock=True)
            if not row:
                return reply('error', 404, _NOT_FOUND, '')
            refusal = rules.review_refusal(row['review_state'], outcome,
                                           row['voided_at'] is not None)
            if refusal:
                return reply('error', 400, refusal, '')
            cur.execute(
                """UPDATE dll_fuel_issues
                      SET review_state = %s, review_note = %s,
                          reviewed_by = %s, reviewed_at = NOW()
                    WHERE issue_uid = %s AND client_uid = %s""",
                (outcome, note, _actor(), issue_uid, client))
            issue = rules.public_issue(_issue(cur, client, issue_uid))
        _audit('FUEL_REVIEW', issue_uid, client,
               {'from': row['review_state'], 'to': outcome, 'note': note})
        return reply('success', 200, 'Review saved', issue)
    except Exception:                   # noqa: BLE001
        log.exception('fuel review failed')
        return reply('error', 500, 'Could not save the review.', '')


@fuel_registry_bp.route('/fuel/issues/<issue_uid>/void', methods=['POST'])
@require_auth
def void_issue(issue_uid):
    reason = str(_body().get('reason') or '').strip()[:rules.NOTES_MAX]
    if len(reason) < 3:
        return _invalid({'reason': 'Say why this issue is being voided.'})
    try:
        with _cursor() as cur:
            client = _client(cur)
            if not client:
                return reply('error', 403, _NO_CLIENT, '')
            row = _issue(cur, client, issue_uid, lock=True)
            if not row:
                return reply('error', 404, _NOT_FOUND, '')
            if row['voided_at'] is not None:
                return reply('error', 400, 'This issue is already voided.', '')
            # A voided issue leaves the review queue; its review, if it had
            # one, stays on the row.
            cur.execute(
                """UPDATE dll_fuel_issues
                      SET voided_at = NOW(), voided_by = %s, void_reason = %s,
                          review_state = CASE WHEN review_state = 'open'
                                              THEN 'none' ELSE review_state END
                    WHERE issue_uid = %s AND client_uid = %s""",
                (_actor(), reason, issue_uid, client))
            issue = rules.public_issue(_issue(cur, client, issue_uid))
        _audit('FUEL_VOID', issue_uid, client, {'reason': reason})
        return reply('success', 200, 'Fuel issue voided', issue)
    except Exception:                   # noqa: BLE001
        log.exception('fuel void failed')
        return reply('error', 500, 'Could not void the fuel issue.', '')


# ── receipt photo ────────────────────────────────────────────────────────────

@fuel_registry_bp.route('/fuel/issues/<issue_uid>/receipt', methods=['POST'])
@require_auth
def upload_receipt(issue_uid):
    upload = request.files.get('photo')
    if upload is None:
        return reply('error', 400, "Send the image in a 'photo' field.", '')
    data = upload.read(rules.RECEIPT_MAX_BYTES + 1)
    if len(data) > rules.RECEIPT_MAX_BYTES:
        return reply('error', 400, 'The photo must be 5 MB or less.', '')
    kind = driver_rules.photo_type(data)
    if kind is None:
        return reply('error', 400, 'The photo must be a JPEG, PNG or WebP image.', '')
    try:
        with _cursor() as cur:
            client = _client(cur)
            if not client:
                return reply('error', 403, _NO_CLIENT, '')
            row = _issue(cur, client, issue_uid, lock=True)
            if not row:
                return reply('error', 404, _NOT_FOUND, '')
            os.makedirs(RECEIPT_DIR, exist_ok=True)
            name = f'{issue_uid}_{uuid.uuid4().hex[:12]}.{kind}'
            with open(os.path.join(RECEIPT_DIR, name), 'wb') as handle:
                handle.write(data)
            cur.execute(
                "UPDATE dll_fuel_issues SET receipt_file = %s "
                "WHERE issue_uid = %s AND client_uid = %s",
                (name, issue_uid, client))
            old = row['receipt_file']
            issue = rules.public_issue(_issue(cur, client, issue_uid))
        if old and old != name:
            try:
                os.remove(os.path.join(RECEIPT_DIR, os.path.basename(old)))
            except OSError:
                pass
        _audit('FUEL_RECEIPT', issue_uid, client)
        return reply('success', 200, 'Receipt saved', issue)
    except Exception:                   # noqa: BLE001
        log.exception('fuel receipt upload failed')
        return reply('error', 500, 'Could not save the receipt.', '')


@fuel_registry_bp.route('/fuel/issues/<issue_uid>/receipt', methods=['GET'])
@require_auth
def get_receipt(issue_uid):
    try:
        with _cursor() as cur:
            client = _client(cur)
            if not client:
                return reply('error', 403, _NO_CLIENT, '')
            row = _issue(cur, client, issue_uid)
        if not row or not row['receipt_file']:
            return reply('error', 404, 'No receipt.', '')
        name = os.path.basename(row['receipt_file'])
        path = os.path.join(RECEIPT_DIR, name)
        if not os.path.isfile(path):
            return reply('error', 404, 'No receipt.', '')
        kind = name.rsplit('.', 1)[-1]
        response = send_file(path, mimetype=driver_rules.PHOTO_MIME.get(kind, 'image/jpeg'))
        response.headers['Cache-Control'] = 'private, max-age=3600'
        return response
    except Exception:                   # noqa: BLE001
        log.exception('fuel receipt get failed')
        return reply('error', 500, 'Could not load the receipt.', '')


# ── summary / suggestions ────────────────────────────────────────────────────

@fuel_registry_bp.route('/fuel/summary', methods=['GET'])
@require_auth
def summary():
    today = _now().date()
    start = _day(request.args.get('from'), today.replace(day=1))
    end = _day(request.args.get('to'), today)
    if end < start:
        start, end = end, start
    if (end - start).days > 366:
        return reply('error', 400, 'Choose at most a year.', '')
    try:
        with _cursor() as cur:
            client = _client(cur)
            if not client:
                return reply('error', 403, _NO_CLIENT, '')
            cur.execute(
                _ISSUE_SELECT + """ WHERE f.client_uid = %s AND f.voided_at IS NULL
                                     AND f.issued_at >= %s AND f.issued_at < %s""",
                (client, datetime.combine(start, datetime.min.time()),
                 datetime.combine(end + timedelta(days=1), datetime.min.time())))
            issues = cur.fetchall()
            cur.execute(
                f"SELECT {_PROFILE_COLUMNS} FROM dll_fuel_vehicle_profiles "
                "WHERE client_uid = %s", (client,))
            profiles = {r['device_imei']: r for r in cur.fetchall()}
        result = rules.summarise(issues, profiles)
        result.update({'from': start.isoformat(), 'to': end.isoformat()})
        return reply('success', 200, 'Fuel summary', result)
    except Exception:                   # noqa: BLE001
        log.exception('fuel summary failed')
        return reply('error', 500, 'Could not load the fuel summary.', '')


@fuel_registry_bp.route('/fuel/stations', methods=['GET'])
@require_auth
def stations():
    try:
        with _cursor() as cur:
            client = _client(cur)
            if not client:
                return reply('error', 403, _NO_CLIENT, '')
            cur.execute(
                """SELECT station_name, COUNT(*) AS n FROM dll_fuel_issues
                    WHERE client_uid = %s AND voided_at IS NULL
                    GROUP BY station_name ORDER BY n DESC, station_name LIMIT 50""",
                (client,))
            names = [r['station_name'] for r in cur.fetchall()]
        return reply('success', 200, 'Stations', names)
    except Exception:                   # noqa: BLE001
        log.exception('fuel stations failed')
        return reply('error', 500, 'Could not load the stations.', '')


# ── reports ──────────────────────────────────────────────────────────────────

def _device_names(imeis):
    """{imei: name} from the unit register; the IMEI itself when unknown."""
    names = {imei: imei for imei in imeis}
    try:
        from .devices import get_cassandra_session
        session = get_cassandra_session()
        stmt = session.prepare("SELECT device_imei, device_name FROM "
                               "dll_device_basic_data WHERE device_imei = ?")
        for imei in imeis:
            row = session.execute(stmt, (imei,)).one()
            if row is not None and row.device_name:
                names[imei] = row.device_name
    except Exception:                   # noqa: BLE001 -- names are a nicety
        log.warning('fuel report: unit names unavailable', exc_info=True)
    return names


@fuel_registry_bp.route('/data-stream/reports/fuel/<kind>/generate-data', methods=['POST'])
@require_auth
def fuel_report_data(kind):
    """The FuelMath reports, in the shape every report route returns:
    [{device_name: [row, ...]}]. Body {data: {report_devices: [imei, ...],
    start_date: DD-MM-YYYY, end_date: DD-MM-YYYY}}. kind is issuance,
    consumption or exceptions (fuel_report.py)."""
    from . import fuel_report
    if kind not in fuel_report.KINDS:
        return reply('error', 404, 'No such fuel report.', '')
    data = _body()
    devices = data.get('report_devices') or []
    if isinstance(devices, str):
        devices = [devices]
    imeis = list(dict.fromkeys(''.join(str(d).split()) for d in devices if d))
    try:
        start = datetime.strptime(str(data.get('start_date')), '%d-%m-%Y').date()
        end = datetime.strptime(str(data.get('end_date')), '%d-%m-%Y').date()
    except ValueError:
        return reply('error', 400, 'Invalid date format. Use DD-MM-YYYY', '')
    if not imeis:
        return reply('error', 400, 'Choose at least one vehicle.', '')
    if end < start:
        start, end = end, start
    if (end - start).days > 366:
        return reply('error', 400, 'Choose at most a year.', '')
    try:
        with _cursor() as cur:
            client = _client(cur)
            if not client:
                return reply('error', 403, _NO_CLIENT, '')
            cur.execute(
                _ISSUE_SELECT + """ WHERE f.client_uid = %s AND f.device_imei = ANY(%s)
                                     AND f.voided_at IS NULL
                                     AND f.issued_at >= %s AND f.issued_at < %s""",
                (client, imeis, datetime.combine(start, datetime.min.time()),
                 datetime.combine(end + timedelta(days=1), datetime.min.time())))
            issues = [rules.public_issue(r) for r in cur.fetchall()]
            cur.execute(
                f"SELECT {_PROFILE_COLUMNS} FROM dll_fuel_vehicle_profiles "
                "WHERE client_uid = %s AND device_imei = ANY(%s)", (client, imeis))
            profiles = {r['device_imei']: r for r in cur.fetchall()}
        rows = fuel_report.rows_for(kind, issues, profiles)
        if not rows:
            return reply('error', 400, fuel_report.EMPTY_MESSAGES[kind], '')
        names = _device_names(list(rows))
        return reply('success', 200, f'Fuel {kind} report',
                     [{names[imei]: rows[imei]} for imei in imeis if imei in rows])
    except Exception:                   # noqa: BLE001
        log.exception('fuel report failed')
        return reply('error', 500, 'Could not build the fuel report.', '')
