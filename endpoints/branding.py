"""
branding.py -- a client's own colours and assistant name for the OLIWA web
console and mobile app (migration 058). Rules in branding_rules.py.

  Any signed-in user
    GET    /branding/me                      the look to paint with, and
                                             whether I may change it
  A client administrator, once staff allow it
    PUT    /branding/me                      {data:{brand_color, accent_color,
                                             assistant_name}} (fields sent)
    DELETE /branding/me                      back to the defaults
  3D Services staff, in the CMS
    GET    /branding/clients/<client_uid>    switches, look, the client's admins
                                             (branding.control or .override)
    PUT    /branding/clients/<client_uid>/control
                                             {data:{enabled, allow_colors,
                                             allow_assistant_name, admin_scope,
                                             allowed_admins}} (branding.control)
    PUT    /branding/clients/<client_uid>    change the look for them
    DELETE /branding/clients/<client_uid>    reset the look (branding.override)

A client is its account_root: the same key the team, alerts and wallet use.
Every change is in the audit log, filed under the client, so it shows in the
client's own Audit trail as well as the CMS audit.
"""

import logging
from contextlib import contextmanager

import psycopg2.extras
from flask import Blueprint, g, request

from . import branding_rules as rules
from . import db_pool
from .globals import (is_customer_account, log_audit_event, reply,
                      require_auth, require_staff)

branding_bp = Blueprint('branding', __name__)
log = logging.getLogger('branding')

_LOOK = ('brand_color', 'accent_color', 'assistant_name')
_CONTROL = ('enabled', 'allow_colors', 'allow_assistant_name', 'admin_scope',
            'allowed_admins')
_REMOVED = 'deactivated'


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


def _body():
    payload = request.get_json(silent=True) or {}
    data = payload.get('data', payload)
    return data if isinstance(data, dict) else {}


def _invalid(errors):
    return reply('error', 400, next(iter(errors.values())), {'errors': errors})


def _settings(cur, client_uid, lock=False):
    cur.execute("SELECT * FROM dll_client_branding WHERE client_uid = %s"
                + (" FOR UPDATE" if lock else ""), (client_uid,))
    return cur.fetchone()


def _upsert(cur, client_uid, fields):
    """Insert the client's row if it has none, then set [fields]."""
    cur.execute("INSERT INTO dll_client_branding (client_uid) VALUES (%s) "
                "ON CONFLICT (client_uid) DO NOTHING", (client_uid,))
    if fields:
        sets = ', '.join(f'{k} = %s' for k in fields)
        cur.execute(f"UPDATE dll_client_branding SET {sets} WHERE client_uid = %s",
                    list(fields.values()) + [client_uid])


def _audit(action, client_uid, meta):
    try:
        log_audit_event(actor=g.current_user['account_uid'], action=action,
                        obj=f'Branding of {client_uid}', domain='CLIENT',
                        tenant_id=client_uid, ip_address=request.remote_addr,
                        meta=meta)
    except Exception:                   # noqa: BLE001 -- never fail the change
        log.exception('branding audit failed')


def _client_user():
    """(account_uid, client_uid, role) for a signed-in client user, or None
    for staff."""
    user = g.current_user
    if not is_customer_account(user.get('role'), user.get('account_type')):
        return None
    root = str(user.get('account_root') or '').strip()
    return (user['account_uid'], root or None, user.get('role'))


def _client_exists(cur, client_uid):
    cur.execute("SELECT 1 FROM dll_client_accounts WHERE client_uid = %s", (client_uid,))
    return cur.fetchone() is not None


def _admins(cur, client_uid):
    """The client's administrators, for the CMS to choose from."""
    cur.execute(
        """SELECT account_uid, log_username, display_name, account_clearance
             FROM dll_access_relay
            WHERE account_root = %s AND COALESCE(access_status, '') <> %s
            ORDER BY date_created""", (client_uid, _REMOVED))
    return [{'account_uid': r['account_uid'],
             'name': r.get('display_name') or r.get('log_username') or r['account_uid'],
             'username': r.get('log_username') or '',
             'role': r.get('account_clearance')}
            for r in cur.fetchall() if rules.is_client_admin(r.get('account_clearance'))]


def _staff_view(cur, client_uid):
    settings = _settings(cur, client_uid)
    saved = settings or {}
    return {
        'client_uid': client_uid,
        'control': rules.control(settings),
        'look': rules.effective(settings),
        'saved': {k: saved.get(k) for k in _LOOK},
        'admins': _admins(cur, client_uid),
        'defaults': rules.defaults(),
        'controlled_by': saved.get('controlled_by'),
        'controlled_at': saved['controlled_at'].isoformat() if saved.get('controlled_at') else None,
        'updated_by': saved.get('updated_by'),
        'updated_at': saved['updated_at'].isoformat() if saved.get('updated_at') else None,
    }


def assistant_name_for(cur, account_uid):
    """The assistant's name for [account_uid]'s client, or the default. Never
    raises and never spoils the caller's transaction: Waswa's own database
    login may not be able to read the table yet."""
    try:
        cur.execute("SAVEPOINT branding_name")
        cur.execute(
            """SELECT b.assistant_name FROM dll_client_branding b
                 JOIN dll_access_relay r ON r.account_root = b.client_uid
                WHERE r.account_uid = %s""", (str(account_uid),))
        row = cur.fetchone()
        cur.execute("RELEASE SAVEPOINT branding_name")
    except Exception:                   # noqa: BLE001
        try:
            cur.execute("ROLLBACK TO SAVEPOINT branding_name")
        except Exception:               # noqa: BLE001
            pass
        return rules.DEFAULT_ASSISTANT
    if not row:
        return rules.DEFAULT_ASSISTANT
    name = row['assistant_name'] if isinstance(row, dict) else row[0]
    return name or rules.DEFAULT_ASSISTANT


# ── a client's own ───────────────────────────────────────────────────────────

@branding_bp.route('/branding/me', methods=['GET'])
@require_auth
def my_branding():
    me = _client_user()
    try:
        if me is None or not me[1]:
            # Staff, or a login with no client: the product's own look.
            out = rules.for_client(None, '', '')
            out.update(can_edit=False, edit_refusal=None)
            return reply('success', 200, 'Branding', out)
        with _cursor() as cur:
            settings = _settings(cur, me[1])
        return reply('success', 200, 'Branding', rules.for_client(settings, me[0], me[2]))
    except Exception:                   # noqa: BLE001
        log.exception('branding read failed')
        # The apps fall back to their defaults on any error, so this costs
        # the look, never the screen.
        return reply('error', 500, 'Could not load the branding.', '')


@branding_bp.route('/branding/me', methods=['PUT'])
@require_auth
def save_my_branding():
    me = _client_user()
    if me is None or not me[1]:
        return reply('error', 403, 'Branding here is for client accounts. '
                     'Staff change it in the CMS.', '')
    account_uid, client_uid, role = me
    try:
        with _cursor() as cur:
            settings = _settings(cur, client_uid, lock=True)
            refusal = rules.edit_refusal(settings, account_uid, role)
            if refusal:
                return reply('error', 403, refusal, '')
            data = {k: v for k, v in _body().items() if k in _LOOK}
            if not data:
                return reply('error', 400, 'Nothing to change.', '')
            clean, errors = rules.validate_look(
                data, settings['allow_colors'], settings['allow_assistant_name'])
            if errors:
                return _invalid(errors)
            _upsert(cur, client_uid, dict(clean, updated_by=account_uid))
            cur.execute("UPDATE dll_client_branding SET updated_at = NOW() "
                        "WHERE client_uid = %s", (client_uid,))
            out = rules.for_client(_settings(cur, client_uid), account_uid, role)
        _audit('BRANDING_UPDATE', client_uid, {'fields': clean})
        return reply('success', 200, 'Branding saved', out)
    except Exception:                   # noqa: BLE001
        log.exception('branding save failed')
        return reply('error', 500, 'Could not save the branding.', '')


@branding_bp.route('/branding/me', methods=['DELETE'])
@require_auth
def reset_my_branding():
    me = _client_user()
    if me is None or not me[1]:
        return reply('error', 403, 'Branding here is for client accounts.', '')
    account_uid, client_uid, role = me
    try:
        with _cursor() as cur:
            settings = _settings(cur, client_uid, lock=True)
            refusal = rules.edit_refusal(settings, account_uid, role)
            if refusal:
                return reply('error', 403, refusal, '')
            # Only what the client may change goes back to the default.
            reset = {}
            if settings['allow_colors']:
                reset.update(brand_color=None, accent_color=None)
            if settings['allow_assistant_name']:
                reset['assistant_name'] = None
            _upsert(cur, client_uid, dict(reset, updated_by=account_uid))
            cur.execute("UPDATE dll_client_branding SET updated_at = NOW() "
                        "WHERE client_uid = %s", (client_uid,))
            out = rules.for_client(_settings(cur, client_uid), account_uid, role)
        _audit('BRANDING_RESET', client_uid, {'fields': sorted(reset)})
        return reply('success', 200, 'Branding reset', out)
    except Exception:                   # noqa: BLE001
        log.exception('branding reset failed')
        return reply('error', 500, 'Could not reset the branding.', '')


# ── staff, in the CMS ────────────────────────────────────────────────────────

def _staff_client(cur, client_uid):
    client_uid = str(client_uid or '').strip()
    return client_uid if client_uid and _client_exists(cur, client_uid) else None


@branding_bp.route('/branding/clients/<client_uid>', methods=['GET'])
@require_staff('branding.control', 'branding.override')
def client_branding(client_uid):
    try:
        with _cursor() as cur:
            if not _staff_client(cur, client_uid):
                return reply('error', 404, 'No such client.', '')
            out = _staff_view(cur, client_uid)
        return reply('success', 200, 'Branding', out)
    except Exception:                   # noqa: BLE001
        log.exception('staff branding read failed')
        return reply('error', 500, 'Could not load the branding.', '')


@branding_bp.route('/branding/clients/<client_uid>/control', methods=['PUT'])
@require_staff('branding.control')
def control_client_branding(client_uid):
    data = {k: v for k, v in _body().items() if k in _CONTROL}
    clean, errors = rules.validate_control(data)
    if errors:
        return _invalid(errors)
    if not clean:
        return reply('error', 400, 'Nothing to change.', '')
    try:
        with _cursor() as cur:
            if not _staff_client(cur, client_uid):
                return reply('error', 404, 'No such client.', '')
            before = rules.control(_settings(cur, client_uid, lock=True))
            after = dict(before, **clean)
            if after['admin_scope'] == 'selected':
                if not after['allowed_admins']:
                    return _invalid({'allowed_admins': 'Choose at least one administrator.'})
                known = {a['account_uid'] for a in _admins(cur, client_uid)}
                strangers = [u for u in after['allowed_admins'] if u not in known]
                if strangers:
                    return _invalid({'allowed_admins':
                                     "Only this client's administrators can be chosen."})
            _upsert(cur, client_uid, dict(clean, controlled_by=g.current_user['account_uid']))
            cur.execute("UPDATE dll_client_branding SET controlled_at = NOW() "
                        "WHERE client_uid = %s", (client_uid,))
            out = _staff_view(cur, client_uid)
        _audit('BRANDING_CONTROL', client_uid,
               {'from': before, 'to': out['control']})
        return reply('success', 200, 'Branding access saved', out)
    except Exception:                   # noqa: BLE001
        log.exception('branding control failed')
        return reply('error', 500, 'Could not save the branding access.', '')


@branding_bp.route('/branding/clients/<client_uid>', methods=['PUT'])
@require_staff('branding.override')
def override_client_branding(client_uid):
    data = {k: v for k, v in _body().items() if k in _LOOK}
    if not data:
        return reply('error', 400, 'Nothing to change.', '')
    clean, errors = rules.validate_look(data)   # staff are not limited by the switches
    if errors:
        return _invalid(errors)
    try:
        with _cursor() as cur:
            if not _staff_client(cur, client_uid):
                return reply('error', 404, 'No such client.', '')
            _upsert(cur, client_uid, dict(clean, updated_by=g.current_user['account_uid']))
            cur.execute("UPDATE dll_client_branding SET updated_at = NOW() "
                        "WHERE client_uid = %s", (client_uid,))
            out = _staff_view(cur, client_uid)
        _audit('BRANDING_OVERRIDE', client_uid, {'fields': clean})
        return reply('success', 200, 'Branding saved', out)
    except Exception:                   # noqa: BLE001
        log.exception('branding override failed')
        return reply('error', 500, 'Could not save the branding.', '')


@branding_bp.route('/branding/clients/<client_uid>', methods=['DELETE'])
@require_staff('branding.override')
def reset_client_branding(client_uid):
    try:
        with _cursor() as cur:
            if not _staff_client(cur, client_uid):
                return reply('error', 404, 'No such client.', '')
            _upsert(cur, client_uid, {'brand_color': None, 'accent_color': None,
                                      'assistant_name': None,
                                      'updated_by': g.current_user['account_uid']})
            cur.execute("UPDATE dll_client_branding SET updated_at = NOW() "
                        "WHERE client_uid = %s", (client_uid,))
            out = _staff_view(cur, client_uid)
        _audit('BRANDING_RESET', client_uid, {'by': 'staff'})
        return reply('success', 200, 'Branding reset', out)
    except Exception:                   # noqa: BLE001
        log.exception('branding reset failed')
        return reply('error', 500, 'Could not reset the branding.', '')
