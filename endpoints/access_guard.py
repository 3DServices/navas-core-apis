"""
access_guard — one check in front of every API route.

Two jobs:

1. Sign-in required everywhere.
   Every route needs a valid JWT except the short PUBLIC list below (sign-in,
   token refresh, password reset, payment-provider webhooks, images).
   Internal services that can't sign in (the alert engine, cron jobs) send the
   shared X-Service-Key header instead.

   AUTH_GATE_MODE controls what happens to a request with no valid sign-in:
     report  (default) - let it through, but log "[auth-gate] would block ..."
                         so you can find any caller that still sends no token.
     enforce           - answer 401.
     off               - no sign-in check (tenant checks below still run).

2. Customers only reach their own data (always on, whatever the mode).
   For a customer login (fleet owner, their team) every ID in the request is
   checked before the route runs:
     - owner IDs (client_uid, owner_uid, account_uid, ...) must be the
       customer's own account or one of its team users;
     - unit IMEIs must be units registered to the customer;
     - object IDs (geofence, event rule, notification, report, payment,
       group, pause rule) must belong to the customer;
     - "show everything" levels (inhouse, service_provider, ussrx, all) are
       refused;
     - staff-only routes (tenants, global statistics, billing dashboards,
       device deletion, SIM stock, ...) answer 403.
   Staff and platform admins are not restricted here.

A refused request gets 403 "This record doesn't belong to your account." and
an ACCESS_DENIED audit event.
"""
import os
import re
import json

import psycopg2
from flask import request, g, current_app

from .globals import (
    reply, _extract_account_uid, _get_user_permissions,
    is_customer_account, _is_platform_admin, log_audit_event,
)


# ── Configuration ────────────────────────────────────────────────────────────

def _mode():
    m = (os.environ.get('AUTH_GATE_MODE') or 'report').strip().lower()
    return m if m in ('report', 'enforce', 'off') else 'report'


def _service_key():
    return (os.environ.get('NAVAS_SERVICE_KEY') or '').strip()


def _norm(rule):
    """'/geozones/<string:owner_uid>/list' -> '/geozones/<owner_uid>/list'"""
    return re.sub(r'<(?:[^:<>]+:)?([^<>]+)>', r'<\1>', rule or '')


# No sign-in needed.
PUBLIC_RULES = frozenset({
    '/',
    '/users/auth',
    '/auth/refresh',
    '/auth/logout',
    '/auth/forgot-password',
    '/auth/reset-password',
    '/auth/mfa/resend',
    '/accounts/users/reset-password',      # proves the old password itself
    '/app/version',
    '/metrics/health',
    # opened by <img> tags and download links, which can't send a token
    '/users/profile-photos/<filename>',
    '/veba/assets/photo/<filename>',
    '/reports-cdn/<access_file>',
    '/tenants/import/template',
    # payment providers call these
    '/payments/transactions/notifications',
    '/system32/payment/webhook',
})

# Machine-to-machine: a staff login or the X-Service-Key header.
INTERNAL_RULES = frozenset({
    '/notifications/log',
    '/pause/rules/run',
    '/devices/sync-client-devices',
    '/subscriptions/auto-renew/run',
    '/alerts/run',
})

# Never available to customer logins.
STAFF_ONLY_PREFIXES = (
    '/tenants/',
    '/clients/',
    '/metrics/',
    '/devices/simcards/',
    '/statistics/debug/',
    '/statistics/clients/',
    '/billing/clients/',
    '/billing/tokens/',
    '/billing/revenue/',
    '/billing/subscriptions/',
)
STAFF_ONLY_RULES = frozenset({
    # whole-platform numbers (the per-client versions stay available)
    '/statistics/tokens/expired',
    '/statistics/tokens/active',
    '/statistics/tokens/paused',
    '/statistics/veba/tokens/active',
    '/statistics/veba/tokens/expired',
    '/statistics/veba/units/enabled',
    '/statistics/veba/units/disabled',
    '/statistics/units/online',
    '/statistics/units/offline',
    '/statistics/sims/summary',
    '/veba/statistics',
    '/ports/activity',
    # delete a unit / block its billing
    '/devices/action',
    '/devices/filter/clients/<client_uid>/network/group/<group_uid>/filter-out',
    # installer and billing operations
    '/configurations/new',
    '/gateways/mobile-money/update',
    '/tokens/subscriptions/update',
    '/subscriptions/token/<token_billing_uid>/devices',
    '/finance/subscriptions/devices/<device_imei>/period/<renewal_period>/account/<account_uid_renewing>/renew',
}) | INTERNAL_RULES

# Self-install flow: the unit isn't registered to the customer yet, so its IMEI
# can't be checked against their fleet. Owner fields are still checked.
UNREGISTERED_IMEI_RULES = frozenset({
    '/system32/payment/check-imei/<imei>',
    '/system32/payment/update-imei',
    '/system32/configurations/new',
})


# ── What each ID means ───────────────────────────────────────────────────────

# URL parameters and body/query fields naming an account.
OWNER_PARAMS = frozenset({
    'client_uid', 'client_id', 'owner_uid', 'transaction_owner', 'reports_owner',
    'account_parent', 'simcard_owner', 'payment_user_uid', 'parent_uid',
    'account_uid_renewing', 'account_uid', 'user_uid', 'uid',
    'service_provider_uid', 'service_provider', 'tenant_id',
})
OWNER_FIELDS = frozenset({
    'account_uid', 'account_root', 'client_uid', 'client', 'owner_uid',
    'event_owner_uid', 'geozone_owner', 'group_owner', 'group_parent_owner',
    'token_buyer', 'commanding_user', 'origin_user', 'request_origin_uid',
    'request_origin_user_uid', 'report_caller', 'primary_account',
    'device_client', 'simcard_owner', 'source_client_uid',
    'destination_client_uid', 'payment_user_uid', 'payment_account_uid',
    'user_authenticating', 'cfg_usr', 'root_account', 'tenant_id',
    'from_tenant_id', 'to_tenant_id',
})

# Unit IMEIs.
DEVICE_PARAMS = frozenset({'device_imei', 'device_id', 'device_uid', 'imei', 'msic_target_device'})
DEVICE_FIELDS = frozenset({'device_imei', 'device_unit', 'imei', 'imei_number', 'used_imei'})
DEVICE_LIST_FIELDS = frozenset({'devices', 'device_list', 'report_devices'})

# "Show everything" switches. Customers may only use these values.
LEVEL_ALLOWED = {
    'data_level': {'client'},
    'access_level': {'client'},
    'level': {'client'},
    'load_level': {'usri'},
    'direction': {'incoming', 'outgoing', 'both'},
}

# Object IDs -> (table, id column, owner column). Chosen by URL prefix because
# the same parameter name is used by different features.
_GEOZONE = ('dll_geozones', 'geozone_uid', 'geozone_owner')
_GEOZONE_GROUP = ('dll_geozone_groups', 'group_uid', 'group_owner')
_DEVICE_GROUP = ('dll_device_groups', 'group_local_uid', 'owner_parent_uid')
_EVENT = ('dll_device_events', 'event_local_uid', 'owner_org_uid')
_NOTIFICATION = ('dll_event_notifications', 'notification_uid', 'owner_uid')
_REPORT = ('dll_reports_downloadable_files', 'request_uid', 'report_caller')
_PAYMENT = ('dll_payment_logs', 'payment_uid', 'payment_account')
_PAUSE_RULE = ('dll_pause_rules', 'id', 'owner_uid')


def _object_kind(rule, param):
    if param == 'geozone_id':
        return _GEOZONE
    if param == 'group_uid':
        return _GEOZONE_GROUP if rule.startswith('/geozones/groups/') else _DEVICE_GROUP
    if param in ('event_uid', 'event_id') and not rule.startswith('/audit/'):
        return _EVENT
    if param == 'notification_uid':
        return _NOTIFICATION
    if param in ('request_uid', 'report_uid') and rule.startswith('/data-stream/reports/'):
        return _REPORT
    if param == 'transaction_uid':
        return _PAYMENT
    if param == 'rule_id' and rule.startswith('/pause/'):
        return _PAUSE_RULE
    return None


# ── The caller's account ─────────────────────────────────────────────────────

class _Denied(Exception):
    def __init__(self, what, value):
        super().__init__(what)
        self.what, self.value = what, value


class _Unavailable(Exception):
    pass


class _Scope:
    """The customer's account, with lookups cached for this request."""

    def __init__(self, account_uid, account_root):
        self.uid = str(account_uid)
        self.root = str(account_root or account_uid)
        self._team = None
        self._conn = None
        self._devices = {}

    # database
    def conn(self):
        if self._conn is None:
            self._conn = psycopg2.connect(current_app.config['db_link'])
        return self._conn

    def close(self):
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass

    def team(self):
        if self._team is None:
            with self.conn().cursor() as cur:
                cur.execute("SELECT account_uid FROM dll_access_relay WHERE account_root = %s",
                            (self.root,))
                self._team = {str(r[0]) for r in cur.fetchall()}
            self.conn().rollback()
        return self._team

    # checks
    def is_own(self, value):
        v = str(value or '').strip()
        if not v:
            return True          # nothing named; the route validates its input
        return v in (self.root, self.uid) or v in self.team()

    def owner_of(self, kind, object_id):
        table, id_col, owner_col = kind
        with self.conn().cursor() as cur:
            cur.execute(f"SELECT {owner_col} FROM {table} WHERE {id_col} = %s LIMIT 1",
                        (str(object_id),))
            row = cur.fetchone()
        self.conn().rollback()
        return None if row is None else (row[0] or '')

    def device_client(self, imei):
        imei = str(imei).strip()
        if imei not in self._devices:
            self._devices[imei] = device_client_lookup(imei)
        return self._devices[imei]


def device_client_lookup(imei):
    """Client UID a unit is registered to ('' when the unit isn't found).
    Raises _Unavailable when the unit registry can't be reached."""
    try:
        from .devices import get_cassandra_session
        session = get_cassandra_session()
    except Exception:
        session = None
    if session is None:
        raise _Unavailable()
    try:
        stmt = session.prepare("SELECT device_client FROM dll_device_basic_data WHERE device_imei = ?")
        row = session.execute(stmt, (imei,)).one()
    except Exception:
        raise _Unavailable()
    return '' if row is None else str(row.device_client or '')


# ── Checks ───────────────────────────────────────────────────────────────────

def _check_owner(scope, what, value):
    if isinstance(value, (list, tuple)):
        for v in value:
            _check_owner(scope, what, v)
        return
    if isinstance(value, (dict, bool)) or value is None:
        return
    if not scope.is_own(value):
        raise _Denied(what, value)


def _check_device(scope, what, value):
    if isinstance(value, (list, tuple)):
        for v in value:
            _check_device(scope, what, v)
        return
    if isinstance(value, dict):
        for key in ('device_imei', 'imei', 'device_unit'):
            if key in value:
                _check_device(scope, what, value[key])
        return
    imei = str(value if value is not None else '').strip()
    if not imei or imei == 'default_option':
        return
    client = scope.device_client(imei)
    if not client or not scope.is_own(client):
        raise _Denied(what, imei)


def _check_object(scope, kind, what, value):
    v = str(value or '').strip()
    if not v:
        return
    owner = scope.owner_of(kind, v)
    if owner is None:
        return                   # doesn't exist - the route answers "not found"
    if not scope.is_own(owner):
        raise _Denied(what, v)


def _check_level(what, value):
    allowed = LEVEL_ALLOWED.get(what)
    if allowed is not None and value not in (None, '') and str(value).lower() not in allowed:
        raise _Denied(what, value)


def _check_target(scope, item):
    """Pause targets: {"scope": "device"|"group", "target": "..."}"""
    if not isinstance(item, dict) or 'target' not in item:
        return
    if str(item.get('scope', 'device')) == 'group':
        _check_object(scope, _DEVICE_GROUP, 'target', item.get('target'))
    else:
        _check_device(scope, 'target', item.get('target'))


def _check_fields(scope, rule, fields):
    skip_imei = rule in UNREGISTERED_IMEI_RULES
    for key, value in fields.items():
        if key in OWNER_FIELDS:
            _check_owner(scope, key, value)
        elif key in DEVICE_FIELDS and not skip_imei:
            _check_device(scope, key, value)
        elif key in DEVICE_LIST_FIELDS:
            _check_device(scope, key, value)
        elif key in LEVEL_ALLOWED:
            _check_level(key, value)
        elif key == 'geozone_uids':
            for z in (value if isinstance(value, list) else [value]):
                _check_object(scope, _GEOZONE, key, z)
        elif key == 'event_uid':
            _check_object(scope, _EVENT, key, value)
        elif key == 'targets' and isinstance(value, list):
            for item in value:
                _check_target(scope, item)
    if 'target' in fields and 'scope' in fields:
        _check_target(scope, fields)


def _body_fields(rule):
    """Top-level JSON fields plus those inside {"data": {...}}."""
    if request.mimetype != 'application/json':
        return {}
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return {}
    fields = {k: v for k, v in body.items() if k != 'data'}
    inner = body.get('data')
    if isinstance(inner, dict):
        fields.update(inner)
    return fields


def check_customer_request(scope, rule, view_args):
    """Raise _Denied if any ID in this request isn't the customer's."""
    if rule in STAFF_ONLY_RULES or rule.startswith(STAFF_ONLY_PREFIXES):
        raise _Denied('route', rule)

    skip_imei = rule in UNREGISTERED_IMEI_RULES
    for name, value in (view_args or {}).items():
        if name in OWNER_PARAMS:
            _check_owner(scope, name, value)
        elif name in DEVICE_PARAMS:
            if not skip_imei:
                _check_device(scope, name, value)
        elif name in LEVEL_ALLOWED:
            _check_level(name, value)
        else:
            kind = _object_kind(rule, name)
            if kind is not None:
                _check_object(scope, kind, name, value)

    _check_fields(scope, rule, {k: request.args.get(k) for k in request.args})
    _check_fields(scope, rule, _body_fields(rule))


# ── The hook ─────────────────────────────────────────────────────────────────

def _client_ip():
    fwd = request.headers.get('X-Forwarded-For', '')
    return fwd.split(',')[0].strip() if fwd else request.remote_addr


def _unauthenticated(rule, why):
    mode = _mode()
    if mode == 'enforce':
        return reply('error', 401, 'Please sign in to continue.', '')
    if mode == 'report':
        print(f"[auth-gate] would block {request.method} {request.path} "
              f"(rule {rule}) from {_client_ip()}: {why}; "
              f"user-agent={request.headers.get('User-Agent', '')[:80]!r}")
    return None


def access_guard():
    if request.method == 'OPTIONS' or request.url_rule is None:
        return None
    rule = _norm(request.url_rule.rule)
    if rule in PUBLIC_RULES:
        return None

    key = _service_key()
    if key and request.headers.get('X-Service-Key', '') == key:
        g.service_call = True
        return None

    account_uid = _extract_account_uid()
    if not account_uid:
        return _unauthenticated(rule, 'no valid token')

    role, account_type, account_root, permissions = _get_user_permissions(account_uid)
    if role is None:
        return _unauthenticated(rule, 'inactive account')

    g.current_user = {
        'account_uid': account_uid,
        'role': role,
        'account_type': account_type,
        'account_root': account_root,
        'permissions': permissions,
    }

    if _is_platform_admin(role, account_type) or not is_customer_account(role, account_type):
        return None

    scope = _Scope(account_uid, account_root)
    try:
        check_customer_request(scope, rule, request.view_args)
    except _Denied as denied:
        log_audit_event(
            actor=account_uid, action='ACCESS_DENIED',
            obj=f"{request.method} {request.path} ({denied.what}={str(denied.value)[:80]})",
            domain='SECURITY', severity='Warn', tenant_id=scope.root,
            ip_address=_client_ip(),
        )
        if denied.what == 'route':
            return reply('error', 403, 'This action is not available to customer accounts.', '')
        return reply('error', 403, "This record doesn't belong to your account.", '')
    except _Unavailable:
        return reply('error', 503, "We couldn't check this unit right now. Please try again.", '')
    finally:
        scope.close()
    return None


def register_access_guard(app):
    app.before_request(access_guard)
