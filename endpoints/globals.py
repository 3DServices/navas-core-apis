from flask import json
from flask import jsonify
from flask import request as flask_request
from flask import g
import psycopg2
import psycopg2.extras
from datetime import datetime
from dateutil.relativedelta import relativedelta
from flask import current_app
from functools import wraps
import pytz
import uuid
import hashlib
from .jwt_utils import decode_access_token

timezone = pytz.timezone('Africa/Nairobi')


# ==========================================
# AUDIT EVENT LOGGER
# ==========================================

def log_audit_event(actor, action, obj, domain, severity='Info', tenant_id=None, ip_address=None, meta=None):
    """
    Insert an audit event into dll_audit_events with hash-chain linking.

    Args:
        actor:      Who performed the action (e.g. account_uid or 'sys.admin')
        action:     What was done (e.g. 'CREATE', 'DELETE', 'LOGIN', 'BLOCK')
        obj:        Human-readable description of what was acted on
        domain:     CMS domain — TENANT, BILLING, VEBA, MONEY, RBAC, TOKEN,
                    PAYMENT, FIRMWARE, SIM, PROTOCOL, ALARM, AI, AUDIT, CLIENT, SYSTEM
        severity:   Info | Warn | Alarm | Crit  (default: Info)
        tenant_id:  Scoped tenant (None for global system events)
        ip_address: Source IP from request
        meta:       Optional dict of extra context (stored as JSONB)
    """
    try:
        dbconnect = psycopg2.connect(current_app.config['db_link'])
        try:
            event_id = 'evt-' + str(uuid.uuid4())[:8]
            now = datetime.utcnow()

            with dbconnect:
                with dbconnect.cursor() as cursor:
                    # Get the last hash for chain linking
                    cursor.execute(
                        "SELECT hash_this FROM dll_audit_events ORDER BY timestamp DESC LIMIT 1"
                    )
                    row = cursor.fetchone()
                    hash_prev = row[0] if row else '0' * 64

                    # Compute current hash (SHA-256 of prev + event data)
                    raw = f"{hash_prev}|{event_id}|{now.isoformat()}|{actor}|{action}|{obj}|{domain}"
                    hash_this = hashlib.sha256(raw.encode()).hexdigest()

                    cursor.execute("""
                        INSERT INTO dll_audit_events
                        (id, timestamp, actor, action, object, domain, severity, tenant_id, ip_address, hash_prev, hash_this, meta)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        event_id, now, str(actor), str(action), str(obj),
                        str(domain), str(severity),
                        str(tenant_id) if tenant_id else None,
                        str(ip_address) if ip_address else None,
                        hash_prev, hash_this,
                        psycopg2.extras.Json(meta) if meta else None
                    ))
        finally:
            dbconnect.close()
    except Exception as e:
        # Never let audit logging break the main request
        print(f"[AUDIT LOG ERROR] {e}")


def reply(status, status_code, message_body, data):

    data_object = {
        "status": status,
        "message": message_body,
        "data": data
    }

    return jsonify(data_object), status_code


# ==========================================
# RBAC MIDDLEWARE
# ==========================================

def _extract_account_uid():
    """
    Extract account_uid from Authorization header (Bearer <JWT> only).

    Returns the 'sub' claim from a valid, non-expired JWT or None.
    Legacy raw-UID and Auth-Key fallbacks have been removed — all
    requests must carry a signed JWT issued by /users/auth or /auth/refresh.
    """
    auth_header = flask_request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return None

    token = auth_header[7:].strip()
    if not token:
        return None

    payload = decode_access_token(token)
    if not payload:
        return None

    return payload.get('sub')


def _get_user_permissions(account_uid):
    """Look up a user's role, account_root, and permissions from the database.

    Returns:
        (user_role, account_type, account_root, permissions)
        or (None, None, None, []) on failure.
    """
    dbconnect = psycopg2.connect(current_app.config['db_link'])
    try:
        with dbconnect:
            with dbconnect.cursor() as cursor:
                # Get user's role name and account_root from dll_access_relay
                cursor.execute(
                    "SELECT account_clearance, account_type, account_root "
                    "FROM dll_access_relay WHERE account_uid = %s AND access_status = 'active'",
                    (str(account_uid),)
                )
                if cursor.rowcount == 0:
                    return None, None, None, []

                row = cursor.fetchone()
                user_role = row[0]
                account_type = row[1]
                account_root = row[2]

                # Get role_uid from role name. If the name lookup misses, try
                # the UID — handles historical rows where create_user wrote a
                # role UID into account_clearance instead of the role name.
                cursor.execute(
                    "SELECT role_uid FROM dll_roles WHERE role_name = %s AND (is_deleted = FALSE OR is_deleted IS NULL)",
                    (str(user_role),)
                )
                if cursor.rowcount == 0:
                    # Fallback: maybe the stored value IS a UID.
                    cursor.execute(
                        "SELECT role_uid FROM dll_roles WHERE role_uid = %s AND (is_deleted = FALSE OR is_deleted IS NULL)",
                        (str(user_role),)
                    )
                    if cursor.rowcount == 0:
                        return user_role, account_type, account_root, []

                role_uid = cursor.fetchone()[0]

                # Get permissions for this role
                cursor.execute(
                    "SELECT p.permission_name FROM dll_role_permissions rp JOIN dll_permissions p ON rp.permission_uid = p.permission_uid WHERE rp.role_uid = %s AND (p.is_deleted = FALSE OR p.is_deleted IS NULL)",
                    (str(role_uid),)
                )
                permissions = [r[0] for r in cursor.fetchall()]
                return user_role, account_type, account_root, permissions
    except Exception:
        return None, None, None, []
    finally:
        dbconnect.close()


def require_permission(*required_perms):
    """
    Decorator that enforces RBAC permission checks on endpoints.

    Usage:
        @require_permission('devices.view')
        def list_devices(): ...

        @require_permission('devices.create', 'devices.edit')  # user needs ANY of these
        def manage_device(): ...

    The decorator:
      1. Extracts account_uid from Authorization header (JWT Bearer token)
      2. Looks up the user's role and permissions
      3. Returns 401 if no valid auth, 403 if missing permission
      4. Sets g.current_user with user info for downstream use
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            account_uid = _extract_account_uid()
            if not account_uid:
                return reply('error', 401, 'Authentication required. Provide Authorization header.', '')

            user_role, account_type, account_root, user_permissions = _get_user_permissions(account_uid)
            if user_role is None:
                return reply('error', 401, 'Invalid or inactive account.', '')

            # Store user context for downstream use
            g.current_user = {
                'account_uid': account_uid,
                'role': user_role,
                'account_type': account_type,
                'account_root': account_root,
                'permissions': user_permissions
            }

            # Super admin and system accounts bypass permission checks
            if user_role in ('super_admin', 'system') or account_type == 'system_account':
                return f(*args, **kwargs)

            # Check if user has ANY of the required permissions
            if required_perms:
                has_permission = any(perm in user_permissions for perm in required_perms)
                if not has_permission:
                    return reply('error', 403, f'Permission denied. Required: {", ".join(required_perms)}', '')

            return f(*args, **kwargs)
        return decorated_function
    return decorator


def require_auth(f):
    """
    Lightweight decorator that only checks authentication (no permission check).
    Sets g.current_user with user info including account_root for tenant scoping.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        account_uid = _extract_account_uid()
        if not account_uid:
            return reply('error', 401, 'Authentication required. Provide Authorization header.', '')

        user_role, account_type, account_root, user_permissions = _get_user_permissions(account_uid)
        if user_role is None:
            return reply('error', 401, 'Invalid or inactive account.', '')

        g.current_user = {
            'account_uid': account_uid,
            'role': user_role,
            'account_type': account_type,
            'account_root': account_root,
            'permissions': user_permissions
        }
        return f(*args, **kwargs)
    return decorated_function


def config_element_data(element, device_imei):

    dbconnect = psycopg2.connect(current_app.config["db_link"])

    try:

        with dbconnect:
            with dbconnect.cursor() as cursor:
                cursor.execute("SELECT config_param_data_source_uid FROM dll_device_local_configs WHERE local_device_imei=%s AND config_parameter=%s;", (str(device_imei), str(element),))

                if(cursor.rowcount == 1):

                    data_adapterx = cursor.fetchone()
                    element_data = data_adapterx[0]

                    cursor.close()

                    return element_data

                else:
                    return 'no_computable_value_found'
                
                    

    except Exception as error:
        return 'error'
    

def config_element_formular_data(element_formular, device_imei):

    dbconnect = psycopg2.connect(current_app.config["db_link"])

    try:

        with dbconnect:
            with dbconnect.cursor() as cursor:
                cursor.execute("SELECT config_formular FROM dll_device_local_configs WHERE local_device_imei=%s AND config_parameter=%s;", (str(device_imei), str(element_formular),))

                if(cursor.rowcount == 1):

                    data_adapter = cursor.fetchone()
                    element_data = data_adapter[0]

                    cursor.close()
                    
                    return element_data

                else:
                    return 'no_computable_fomular_found'

    except Exception as error:
        return 'error'



def compare_years(start_date, end_date):
    start = datetime.strptime(start_date, "%d-%m-%Y")
    end = datetime.strptime(end_date, "%d-%m-%Y")

    diff_years = end.year - start.year

    if diff_years == 0:
        return True
    elif diff_years == 1:
        return True
    elif diff_years == 2:
        return True
        
    else:
        return False
    


def check_device(device_imei):

    dbconnect = psycopg2.connect(current_app.config['db_link'])

    with dbconnect:
        with dbconnect.cursor() as cursor:
            cursor.execute("SELECT device_billing_status FROM dll_device_basic_data WHERE device_imei=%s;", (str(device_imei),))

            if(cursor.rowcount == 1):

                Device_BillingObject = cursor.fetchone()
                BillingStatus = Device_BillingObject[0]

                return BillingStatus

            elif(cursor.rowcount == 0):
                return 'not-found'
            

def CheckHardware(device_imei):

    dbconnect = psycopg2.connect(current_app.config['db_link'])

    with dbconnect:
        with dbconnect.cursor() as cursor:
            cursor.execute("SELECT device_hardware,device_vendor FROM dll_device_registrar WHERE device_imei=%s;", (str(device_imei),))

            if(cursor.rowcount == 1):

                Device_dataAdapter = cursor.fetchone()
                DeviceHardware = Device_dataAdapter[0]

                return DeviceHardware

            elif(cursor.rowcount == 0):
                return 'not-found'


def CheckHardware2(device_imei):

    dbconnect = psycopg2.connect(current_app.config['db_link'])

    with dbconnect:
        with dbconnect.cursor() as cursor:
            cursor.execute("SELECT device_hardware,device_vendor FROM dll_device_registrar WHERE device_imei=%s;", (str(device_imei),))

            if(cursor.rowcount == 1):

                Device_dataAdapter = cursor.fetchone()
                DeviceHardware = Device_dataAdapter[0]
                DeviceVendor = Device_dataAdapter[1]

                Back = {
                    "vendor": DeviceVendor,
                    "hardware": DeviceHardware
                }

                return DeviceVendor

            elif(cursor.rowcount == 0):
                return 'not-found'
            

def NextRenewal(months):
    current_date = datetime.now()
    future_date = current_date + relativedelta(months=months)
    return future_date.strftime("%Y-%m-%d")


def SubscriptionManager(UserID, TokenAttached, ImeiNumber):
    try:
        _dbconnect = psycopg2.connect(current_app.config['db_link'])

        with _dbconnect:
            with _dbconnect.cursor() as cursor:
                cursor.execute("SELECT token_hours_left FROM dll_user_token_accounts WHERE token_billing_uid=%s", (str(TokenAttached),))

                if(cursor.rowcount == 1):
                    
                    _TunnelData = cursor.fetchone()
                    _TokenHours_Left = _TunnelData[0]

                    print(f"Token Hours Left: {_TokenHours_Left}")

                    if(int(_TokenHours_Left) >= 1):
                        current_time = datetime.now(timezone).strftime("%I:%M:%S%p")
                        currentLocal_Date = datetime.now(timezone).strftime("%d-%m-%Y")

                        cursor.execute("SELECT id FROM dll_device_subscriptions WHERE device_imei_number=%s", (str(ImeiNumber),))
                        if(cursor.rowcount == 0):
                            cursor.execute("INSERT INTO dll_device_subscriptions (device_imei_number, subscription_status, start_date, start_counting_time, service_provider, token_billing_uid) VALUES(%s, %s, TO_DATE(%s, 'DD-MM-YYYY'), %s, %s, %s)", (str(ImeiNumber), 'active', str(currentLocal_Date), str(current_time), '3D_SERVICES_CORE', str(TokenAttached)))
                        
                        return "success-proceed"

                    elif(int(_TokenHours_Left) < 1):
                        return "token-expired"

                else:
                    return "token-not-found"

    except Exception as error:
        print(f"ERROR : {error}")
        #return "error-reject"
        return str(error)
