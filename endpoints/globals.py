from flask import json
from flask import jsonify
from flask import request as flask_request
from flask import g
from flask import has_app_context
import psycopg2
import psycopg2.extras
from datetime import datetime
from dateutil.relativedelta import relativedelta
from flask import current_app
from functools import wraps
import pytz
import uuid
import hashlib
import logging
import re
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


# ==========================================
# CREDENTIAL SCRUBBER  (B10)
# ==========================================
#
# Every error path in this codebase funnels through reply().  71 handlers pass
# str(error) as the message body, and a malformed db_link makes psycopg2 quote
# the password back inside its own error text.  scrub_secrets() is the single
# place that gets removed.
#
# It is deliberately a PURE function -- no Flask, no database, no module state
# -- so tests/test_reply_scrub.py can exercise it without an app context.

# scheme://user:password@host   and the malformed  scheme:/user:password@host
_CREDENTIAL_URI = re.compile(
    r'(?P<scheme>[A-Za-z][A-Za-z0-9+.\-]*:/{1,3})(?P<user>[^\s:/@]*):(?P<secret>[^\s@]+)@'
)

# psycopg2 keyword DSN form:  dbname=x user=y password=z host=w
_CREDENTIAL_KEYWORD = re.compile(r'(?P<key>password\s*=\s*)(?P<secret>\S+)')

# Only treat `password=` as a DSN field when another libpq keyword is present.
# Without this guard an ordinary sentence -- "Invalid password = required" --
# would be rewritten, which would change a message for no security gain.  The
# configured-secret pass still covers a lone `password=SECRET`.
_DSN_CONTEXT = re.compile(r'\b(?:dbname|host|hostaddr|port|user|sslmode|options)\s*=')

REDACTED = '***'


def scrub_secrets(text, extra=()):
    """Remove credentials from a value before it leaves the process.

    Three passes, in order:
      1. scheme://user:password@host  ->  scheme://user:***@host
      2. password=SECRET  ->  password=***  (only inside a libpq DSN)
      3. every literal in `extra` (the configured secrets) -> ***

    Pass 3 is the backstop: it catches a secret embedded in a shape passes 1
    and 2 do not recognise.  Strings shorter than 4 characters are skipped so
    a trivially short configured value cannot blank out unrelated text.

    Containers are walked so a handler that nests the error text one level
    deep is covered too.  Types are preserved; anything that is not a string
    or a container is returned untouched.
    """
    if isinstance(text, str):
        cleaned = _CREDENTIAL_URI.sub(
            lambda m: m.group('scheme') + m.group('user') + ':' + REDACTED + '@',
            text,
        )
        if _DSN_CONTEXT.search(cleaned):
            cleaned = _CREDENTIAL_KEYWORD.sub(
                lambda m: m.group('key') + REDACTED,
                cleaned,
            )
        for secret in (extra or ()):
            if isinstance(secret, str) and len(secret) >= 4:
                cleaned = cleaned.replace(secret, REDACTED)
        return cleaned

    if isinstance(text, dict):
        return dict((key, scrub_secrets(value, extra)) for key, value in text.items())

    if isinstance(text, list):
        return [scrub_secrets(item, extra) for item in text]

    if isinstance(text, tuple):
        return tuple(scrub_secrets(item, extra) for item in text)

    return text


def _configured_secrets():
    """The secret halves of this app's configured db_link, as literals.

    Never raises: outside an app context, or with db_link absent, it simply
    returns an empty tuple and pattern matching alone does the work.
    """
    secrets = []

    try:
        if not has_app_context():
            return ()

        link = current_app.config.get('db_link')

        if link:
            link = str(link)

            found = _CREDENTIAL_URI.search(link)

            if found:
                secrets.append(found.group('secret'))

            found = _CREDENTIAL_KEYWORD.search(link)

            if found:
                secrets.append(found.group('secret'))

    except Exception:
        return tuple(secrets)

    return tuple(secrets)


def reply(status, status_code, message_body, data):

    safe_message = scrub_secrets(message_body, _configured_secrets())

    if safe_message != message_body:
        logging.warning(
            'reply(): credentials redacted from a %s response body', status_code
        )

    data_object = {
        "status": status,
        "message": safe_message,
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

    Cached for the rest of the request, so the access guard and the route's
    decorator share one lookup.
    """
    try:
        cached = getattr(g, '_user_permissions', None)
    except RuntimeError:
        cached = None
    if cached and cached[0] == str(account_uid):
        return cached[1]
    result = _load_user_permissions(account_uid)
    try:
        g._user_permissions = (str(account_uid), result)
    except RuntimeError:
        pass
    return result


def _load_user_permissions(account_uid):
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


# ── Customer accounts ─────────────────────────────────────────────────────────
# Customers (fleet owners using OLIWA and the mobile app) never skip permission
# checks. Their role names are shared with staff ("admin" exists in both), so
# the role's database permissions can't be trusted for them either: a customer
# may use exactly the endpoints below, which act on their own fleet, and
# nothing else. Staff-only endpoints (clients, users, RBAC, audit, token and
# product catalogue changes) answer 403 to every customer account.
CUSTOMER_ROLES = frozenset({'customer', 'customer_tracker'})
CUSTOMER_ACCOUNT_TYPES = frozenset({'client', 'customer', 'customer_tracker'})
CUSTOMER_PERMISSIONS = frozenset({
    # their own devices, balance, subscriptions and payments
    'devices.view', 'devices.command',
    'tokens.view_balance',
    'subscriptions.view_status', 'subscriptions.renew',
    'finance.view',
    # buying their own tokens — /payments/tokens/buy
    'finance.create',
    'products.view_only', 'products.variants.view_only',
    # VEBA marketplace
    'can_browse_asset_listings', 'can_list_asset_on_marketplace',
    'can_edit_asset_listing', 'can_view_unit_digital_twin',
    'can_book_asset', 'can_view_booking',
    'can_approve_booking_request', 'can_reject_booking_request',
    'can_archive_booking_request', 'can_delete_booking_request',
})


def is_customer_account(role, account_type):
    """True for a fleet customer's login (including a customer org's admin)."""
    return (str(role or '').lower() in CUSTOMER_ROLES
            or str(account_type or '').lower() in CUSTOMER_ACCOUNT_TYPES)


def _is_platform_admin(role, account_type):
    return role in ('super_admin', 'system') or account_type == 'system_account'


def resolve_wallet_owner(cursor, uid):
    """Map any account uid to the client wallet it belongs to.

    A client's tokens live in dll_user_token_accounts keyed by client_uid,
    which is dll_access_relay.account_root (rbac.py joins the two columns
    directly). But a login under that client carries its own account_uid, and
    the OLIWA console asked for the balance with that account_uid. For the
    account owner the two happen to be equal, so it looked right; for every
    other user of the same company the client lookup missed and the console
    showed an empty wallet.

    The console also tagged purchases with the signed-in account_uid, and the
    payment webhook credits whatever uid it finds on the payment row — so some
    real tokens are keyed by a user rather than the company. Those rows are
    part of the same wallet and are counted here, rather than being stranded.

    Returns (client_uid, owner_uids) — the canonical client account, and every
    uid that may hold a row belonging to it. Widening to the account family is
    not a widening of access: the guard in access_guard.py has already checked
    that a customer may only name their own account, root or team.
    """
    uid = str(uid or '').strip()

    cursor.execute(
        "SELECT account_root FROM dll_access_relay WHERE account_uid=%s",
        (uid,)
    )
    row = cursor.fetchone()
    root = str(row[0]).strip() if row and row[0] else ''
    client_uid = root or uid

    cursor.execute(
        "SELECT account_uid FROM dll_access_relay WHERE account_root=%s",
        (client_uid,)
    )
    owners = {client_uid, uid}
    owners.update(str(r[0]).strip() for r in cursor.fetchall() if r[0])
    owners.discard('')
    return client_uid, sorted(owners)


def resolve_client_account(cursor, uid):
    """The CLIENT account that should own tokens bought or granted for [uid].

    Tokens belong to companies. Every row in dll_user_token_accounts is keyed
    by client_uid, and every balance screen, subscription check and renewal
    sweep reads it by that key — so a credit written under anything that is
    not a client account creates a wallet nobody can ever see, and money that
    was really taken buys tokens that never appear.

    [uid] may be a client account, a login belonging to one (a company's own
    staff, whose account_root is the company), or the client a member of 3D
    Services staff picked when buying on a customer's behalf. All three
    resolve to the same place. Anything else — a staff login with no client
    behind it, a typo, a deleted company — returns None, and the caller must
    refuse rather than write the row.
    """
    client_uid, _ = resolve_wallet_owner(cursor, uid)
    if not client_uid:
        return None
    cursor.execute(
        "SELECT client_uid FROM dll_client_accounts WHERE client_uid=%s",
        (client_uid,)
    )
    return client_uid if cursor.fetchone() else None


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

            # Super admin and system accounts bypass permission checks.
            if _is_platform_admin(user_role, account_type):
                return f(*args, **kwargs)

            # Customers: only the customer allow-list, whatever their role says.
            if is_customer_account(user_role, account_type):
                if required_perms and not any(p in CUSTOMER_PERMISSIONS for p in required_perms):
                    return reply('error', 403, 'This action is not available to customer accounts.', '')
                return f(*args, **kwargs)

            # Check if user has ANY of the required permissions
            if required_perms:
                has_permission = any(perm in user_permissions for perm in required_perms)
                if not has_permission:
                    return reply('error', 403, f'Permission denied. Required: {", ".join(required_perms)}', '')

            return f(*args, **kwargs)
        return decorated_function
    return decorator


def require_permission_or_self(param, *required_perms):
    """require_permission, except that a signed-in user may always read their
    OWN record without holding the permission.

    GET /users/<account_uid>/details required 'users.view'. Customers do not
    have it and must not be given it: /users/allx takes no owner parameter, so
    the access guard cannot scope that route and the permission is the only
    thing keeping the platform's whole user list private. The side effect was
    that a customer could not open their own profile — the mobile app's
    Profile screen 403'd for every fleet owner.

    Reading your own record needs no capability: you are the record. Anyone
    asking for somebody else's still goes through the normal check.

    [param] is the name of the URL parameter holding the account uid.
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            account_uid = _extract_account_uid()
            if not account_uid:
                return reply('error', 401,
                             'Authentication required. Provide Authorization header.', '')
            if str(kwargs.get(param) or '') == str(account_uid):
                # Still populate g.current_user for anything downstream.
                role, account_type, account_root, permissions = \
                    _get_user_permissions(account_uid)
                if role is None:
                    return reply('error', 401, 'Invalid or inactive account.', '')
                g.current_user = {
                    'account_uid': account_uid,
                    'role': role,
                    'account_type': account_type,
                    'account_root': account_root,
                    'permissions': permissions,
                }
                return f(*args, **kwargs)
            # Somebody else's record — the ordinary rules apply. The permission
            # lookup is cached on g, so this costs nothing extra.
            return require_permission(*required_perms)(f)(*args, **kwargs)
        return decorated_function
    return decorator


def require_staff(*required_perms):
    """
    For endpoints that act across tenants (all payments, moving tokens between
    clients): refuses every customer account, then applies the normal
    permission check for staff.
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

            g.current_user = {
                'account_uid': account_uid,
                'role': user_role,
                'account_type': account_type,
                'account_root': account_root,
                'permissions': user_permissions
            }

            if is_customer_account(user_role, account_type):
                return reply('error', 403, 'This action is only available to 3D Services staff.', '')
            if _is_platform_admin(user_role, account_type):
                return f(*args, **kwargs)
            if required_perms and not any(p in user_permissions for p in required_perms):
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
    


# ── One connection per request, for the read-only device lookups ────────────
# check_device, CheckHardware and CheckHardware2 are called several times per
# request and each used to open its own connection. Against this host a
# connect costs ~2.3s, so a single trips_history request spent ~7s of its 30
# doing nothing but handshakes.
#
# RESERVED FOR READS. These three helpers are pure SELECTs. Do NOT hand this
# connection to anything that writes: every caller wraps its work in
# `with dbconnect:`, which COMMITS, so a writer sharing this connection would
# commit whatever else happened to be pending on it. The ~190 functions in
# this codebase that open their own connection need a pool and a review of
# what each transaction spans; that is deliberately not this change.
_READ_CONN_KEY = '_navas_read_only_connection'


def _read_connection():
    """The request's shared read-only connection, opening it on first use.

    Outside an app context — a script importing this module — a fresh
    connection is returned instead, so existing callers keep working.
    """
    if not has_app_context():
        return psycopg2.connect(current_app.config['db_link'])
    existing = getattr(g, _READ_CONN_KEY, None)
    if existing is not None and not existing.closed:
        return existing
    fresh = psycopg2.connect(current_app.config['db_link'])
    setattr(g, _READ_CONN_KEY, fresh)
    return fresh


def close_read_connection(_exception=None):
    """Close the shared read connection at the end of the app context.

    Registered in app.py. Without this the connection would be left to
    CPython's refcounting, which is what the audit flagged as fragile even
    though it currently works.
    """
    existing = getattr(g, _READ_CONN_KEY, None) if has_app_context() else None
    if existing is None:
        return
    try:
        if not existing.closed:
            existing.close()
    except Exception:                                   # noqa: BLE001
        pass
    try:
        setattr(g, _READ_CONN_KEY, None)
    except Exception:                                   # noqa: BLE001
        pass


def check_device(device_imei):

    dbconnect = _read_connection()

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

    dbconnect = _read_connection()

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

    dbconnect = _read_connection()

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
                cursor.execute("SELECT token_units_left FROM dll_user_token_accounts WHERE token_billing_uid=%s", (str(TokenAttached),))

                if(cursor.rowcount == 1):
                    
                    _TunnelData = cursor.fetchone()
                    _TokenUnits_Left = _TunnelData[0]

                    print(f"Token Units Left: {_TokenUnits_Left}")

                    if(_TokenUnits_Left == "units_unfined_waiting_for_first_use"):
                        
                        current_time = datetime.now(timezone).strftime("%I:%M:%S%p")
                        currentLocal_Date = datetime.now(timezone).strftime("%d-%m-%Y")

                        cursor.execute("SELECT id FROM dll_device_subscriptions WHERE device_imei_number=%s", (str(ImeiNumber),))
                        if(cursor.rowcount == 0):
                            cursor.execute("INSERT INTO dll_device_subscriptions (device_imei_number, subscription_status, start_date, start_counting_time, service_provider, token_billing_uid) VALUES(%s, %s, TO_DATE(%s, 'DD-MM-YYYY'), %s, %s, %s)", (str(ImeiNumber), 'active', str(currentLocal_Date), str(current_time), '3D_SERVICES_CORE', str(TokenAttached)))
                        
                        return "success-proceed"

                    else:
                        return "token-expired"

                else:
                    return "token-not-found"

    except Exception as error:
        print(f"ERROR : {error}")
        #return "error-reject"
        return str(error)
