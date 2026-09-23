"""
team.py — a customer's own team: the people in one client account.

A client (e.g. Mukwano Co Ltd) can have many users helping to monitor its
fleet. The client's administrators manage those users here, and see who signed
in and when — all limited to their own account (account_root). Nothing here
reaches another client's users or events.

    GET    /team/me                               who am I, may I manage the team
    GET    /team/members                          users in my account
    POST   /team/members                          add a user
    PUT    /team/members/<uid>                    change name / role / block, unblock
    POST   /team/members/<uid>/reset-password     new temporary password
    DELETE /team/members/<uid>                    remove (deactivate) a user
    GET    /team/audit?days=30&kind=all           sign-ins and team changes

Team roles (stored in dll_access_relay.account_clearance):

    client_admin     everything, plus managing the team and reading the audit
    client_operator  monitor the fleet and manage geofences, alerts, bookings
    client_viewer    look only

The account's original login (customer / customer_tracker, or a customer org's
"admin") counts as a client_admin.

Staff manage users in the CMS; these endpoints are for customer accounts only.
"""

import datetime
import logging
import re
import secrets
import string
import uuid

import bcrypt
import psycopg2
from flask import Blueprint, current_app, g, request

from .globals import (reply, require_auth, log_audit_event,
                      is_customer_account)

team_bp = Blueprint('team_bp', __name__)
_log = logging.getLogger('team')

TEAM_ROLES = {
    'client_admin': 'Administrator',
    'client_operator': 'Operator',
    'client_viewer': 'Viewer',
}
# The account's first login and a customer org's own admin manage the team too.
TEAM_ADMIN_ROLES = frozenset({'client_admin', 'customer', 'customer_tracker', 'admin'})

_USERNAME = re.compile(r'^[A-Za-z0-9._@-]{3,60}$')
_EMAIL = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
_REMOVED = 'deactivated'


class TeamError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def _db():
    return psycopg2.connect(current_app.config['db_link'])


def _me():
    """The signed-in customer, or a TeamError."""
    user = g.current_user
    if not is_customer_account(user['role'], user['account_type']):
        raise TeamError('Team management here is for customer accounts. '
                        'Staff manage users in the CMS.', 403)
    if not user.get('account_root'):
        raise TeamError('Your login is not linked to a client account.', 403)
    return user


def _can_manage(user):
    return str(user['role'] or '').lower() in TEAM_ADMIN_ROLES


def _admin():
    user = _me()
    if not _can_manage(user):
        raise TeamError('Only your account administrators can manage the team.', 403)
    return user


def _role_label(role):
    role = str(role or '')
    if role in TEAM_ROLES:
        return TEAM_ROLES[role]
    if role.lower() in TEAM_ADMIN_ROLES:
        return 'Administrator'
    return role or '—'


def _row_to_member(columns, row, me_uid):
    r = dict(zip(columns, row))
    # dll_access_relay keeps email and creator by position (see users.py).
    email = row[6] if len(row) > 6 else ''
    last = r.get('last_login_at')
    role = r.get('account_clearance')
    return {
        'account_uid': r.get('account_uid'),
        'display_name': r.get('display_name') or r.get('log_username') or '',
        'username': r.get('log_username') or '',
        'email': email or '',
        'role': role,
        'role_label': _role_label(role),
        'is_admin': str(role or '').lower() in TEAM_ADMIN_ROLES,
        'status': r.get('access_status') or '',
        'date_created': str(r.get('date_created') or ''),
        'last_login_at': last.isoformat() if hasattr(last, 'isoformat') else (str(last) if last else None),
        'is_me': r.get('account_uid') == me_uid,
    }


def _target(cursor, root, uid):
    cursor.execute("SELECT * FROM dll_access_relay WHERE account_uid = %s AND account_root = %s",
                   (str(uid), str(root)))
    row = cursor.fetchone()
    if not row or row[4] == _REMOVED:
        raise TeamError('That user is not in your team.', 404)
    return [d[0] for d in cursor.description], row


def _audit(user, action, obj, meta=None):
    log_audit_event(actor=user['account_uid'], action=action, obj=obj,
                    domain='TEAM', severity='Info', tenant_id=user['account_root'],
                    ip_address=request.remote_addr, meta=meta)


def _handle(fn):
    try:
        return fn()
    except TeamError as error:
        return reply('error', error.status, str(error), '')
    except Exception as error:      # noqa: BLE001
        _log.exception('team request failed: %s', error)
        return reply('error', 500, 'Something went wrong. Please try again.', '')


# ── Who am I ────────────────────────────────────────────────────────────────

@team_bp.route('/team/me', methods=['GET'])
@require_auth
def team_me():
    def run():
        user = _me()
        return reply('success', 200, 'OK', {
            'account_uid': user['account_uid'],
            'account_root': user['account_root'],
            'role': user['role'],
            'role_label': _role_label(user['role']),
            'can_manage_team': _can_manage(user),
            'roles': [{'role': k, 'label': v} for k, v in TEAM_ROLES.items()],
        })
    return _handle(run)


# ── Members ─────────────────────────────────────────────────────────────────

@team_bp.route('/team/members', methods=['GET'])
@require_auth
def team_members():
    def run():
        user = _admin()
        conn = _db()
        try:
            with conn, conn.cursor() as cur:
                cur.execute("SELECT * FROM dll_access_relay WHERE account_root = %s "
                            "AND COALESCE(access_status, '') <> %s ORDER BY date_created",
                            (user['account_root'], _REMOVED))
                cols = [d[0] for d in cur.description]
                members = [_row_to_member(cols, r, user['account_uid']) for r in cur.fetchall()]
        finally:
            conn.close()
        return reply('success', 200, f'{len(members)} team member(s)', members)
    return _handle(run)


@team_bp.route('/team/members', methods=['POST'])
@require_auth
def team_add():
    def run():
        user = _admin()
        data = (request.get_json(silent=True) or {}).get('data') or {}
        name = str(data.get('display_name') or '').strip()
        username = str(data.get('username') or '').strip()
        email = str(data.get('email') or '').strip()
        password = str(data.get('password') or '')
        role = str(data.get('role') or 'client_viewer')

        if len(name) < 2:
            raise TeamError('Enter the person\'s full name.')
        if not _USERNAME.match(username):
            raise TeamError('Username: 3–60 letters, numbers, dots, dashes, underscores or @.')
        if email and not _EMAIL.match(email):
            raise TeamError('That email address doesn\'t look right.')
        if len(password) < 8:
            raise TeamError('The password must be at least 8 characters.')
        if role not in TEAM_ROLES:
            raise TeamError('Choose Administrator, Operator or Viewer.')

        conn = _db()
        try:
            with conn, conn.cursor() as cur:
                cur.execute("SELECT 1 FROM dll_access_relay WHERE log_username = %s", (username,))
                if cur.rowcount:
                    raise TeamError('That username is already taken. Try another.', 409)
                new_uid = str(uuid.uuid4())
                hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
                # Same column order as users.py create_user.
                cur.execute(
                    "INSERT INTO dll_access_relay VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (user['account_root'], new_uid, user['account_type'], role, 'active',
                     datetime.datetime.now().date(), email, user['account_uid'], username,
                     hashed, name, 'no', 'no', 'no',
                     'column_deprecated_use_billing_type_instead', '0'))
        finally:
            conn.close()
        _audit(user, 'TEAM_USER_ADDED', f"Added {name} ({username}) as {TEAM_ROLES[role]}",
               {'account_uid': new_uid, 'role': role})
        return reply('success', 200, f'{name} can now sign in as {username}.',
                     {'account_uid': new_uid})
    return _handle(run)


@team_bp.route('/team/members/<uid>', methods=['PUT'])
@require_auth
def team_update(uid):
    def run():
        user = _admin()
        data = (request.get_json(silent=True) or {}).get('data') or {}
        conn = _db()
        changes = []
        try:
            with conn, conn.cursor() as cur:
                cols, row = _target(cur, user['account_root'], uid)
                member = _row_to_member(cols, row, user['account_uid'])
                is_me = member['is_me']

                if 'display_name' in data:
                    name = str(data['display_name'] or '').strip()
                    if len(name) < 2:
                        raise TeamError('Enter the person\'s full name.')
                    cur.execute("UPDATE dll_access_relay SET display_name = %s WHERE account_uid = %s",
                                (name, uid))
                    changes.append(f'name to {name}')

                if 'role' in data and data['role'] != member['role']:
                    role = str(data['role'])
                    if role not in TEAM_ROLES:
                        raise TeamError('Choose Administrator, Operator or Viewer.')
                    if is_me:
                        raise TeamError('You can\'t change your own role. Ask another administrator.')
                    cur.execute("UPDATE dll_access_relay SET account_clearance = %s WHERE account_uid = %s",
                                (role, uid))
                    changes.append(f'role to {TEAM_ROLES[role]}')

                if 'status' in data and data['status'] != member['status']:
                    status = str(data['status'])
                    if status not in ('active', 'blocked'):
                        raise TeamError('Status must be active or blocked.')
                    if is_me:
                        raise TeamError('You can\'t block yourself.')
                    cur.execute("UPDATE dll_access_relay SET access_status = %s WHERE account_uid = %s",
                                (status, uid))
                    changes.append('unblocked' if status == 'active' else 'blocked')
        finally:
            conn.close()
        if not changes:
            return reply('success', 200, 'Nothing changed.', '')
        _audit(user, 'TEAM_USER_CHANGED',
               f"Changed {member['display_name']} ({member['username']}): {', '.join(changes)}",
               {'account_uid': uid})
        return reply('success', 200, 'Saved.', '')
    return _handle(run)


@team_bp.route('/team/members/<uid>/reset-password', methods=['POST'])
@require_auth
def team_reset_password(uid):
    def run():
        user = _admin()
        alphabet = string.ascii_letters + string.digits
        temp = ''.join(secrets.choice(alphabet) for _ in range(12))
        conn = _db()
        try:
            with conn, conn.cursor() as cur:
                cols, row = _target(cur, user['account_root'], uid)
                member = _row_to_member(cols, row, user['account_uid'])
                cur.execute("UPDATE dll_access_relay SET log_password = %s WHERE account_uid = %s",
                            (bcrypt.hashpw(temp.encode(), bcrypt.gensalt()).decode(), uid))
        finally:
            conn.close()
        _audit(user, 'TEAM_PASSWORD_RESET',
               f"Reset the password of {member['display_name']} ({member['username']})",
               {'account_uid': uid})
        return reply('success', 200, 'Share this password with them securely. It is shown once.',
                     {'temporary_password': temp, 'username': member['username']})
    return _handle(run)


@team_bp.route('/team/members/<uid>', methods=['DELETE'])
@require_auth
def team_remove(uid):
    def run():
        user = _admin()
        conn = _db()
        try:
            with conn, conn.cursor() as cur:
                cols, row = _target(cur, user['account_root'], uid)
                member = _row_to_member(cols, row, user['account_uid'])
                if member['is_me']:
                    raise TeamError('You can\'t remove yourself.')
                cur.execute("UPDATE dll_access_relay SET access_status = %s WHERE account_uid = %s",
                            (_REMOVED, uid))
        finally:
            conn.close()
        _audit(user, 'TEAM_USER_REMOVED',
               f"Removed {member['display_name']} ({member['username']}) from the team",
               {'account_uid': uid})
        return reply('success', 200, f"{member['display_name']} can no longer sign in.", '')
    return _handle(run)


# ── Audit: who signed in, and when ──────────────────────────────────────────

_KINDS = {
    'signins': ('LOGIN', 'LOGOUT'),
    'failed': ('LOGIN_FAILED',),
    'team': ('TEAM_USER_ADDED', 'TEAM_USER_CHANGED', 'TEAM_PASSWORD_RESET', 'TEAM_USER_REMOVED'),
}


@team_bp.route('/team/audit', methods=['GET'])
@require_auth
def team_audit():
    def run():
        user = _admin()
        try:
            days = max(1, min(int(request.args.get('days', 30)), 365))
        except ValueError:
            days = 30
        kind = request.args.get('kind', 'all')
        since = datetime.datetime.utcnow() - datetime.timedelta(days=days)

        conn = _db()
        try:
            with conn, conn.cursor() as cur:
                # Everyone who is or was in this account, to name them and to
                # catch events logged without a tenant (logout, failed sign-in).
                cur.execute("SELECT account_uid, log_username, display_name FROM dll_access_relay "
                            "WHERE account_root = %s", (user['account_root'],))
                people = cur.fetchall()
                by_uid = {p[0]: (p[2] or p[1]) for p in people}
                by_username = {p[1]: (p[2] or p[1]) for p in people if p[1]}

                sql = ("SELECT timestamp, actor, action, object, ip_address FROM dll_audit_events "
                       "WHERE timestamp >= %s AND (tenant_id = %s OR actor = ANY(%s) "
                       "OR (action = 'LOGIN_FAILED' AND actor = ANY(%s)))")
                params = [since, user['account_root'], list(by_uid), list(by_username)]
                if kind in _KINDS:
                    sql += " AND action = ANY(%s)"
                    params.append(list(_KINDS[kind]))
                sql += " ORDER BY timestamp DESC LIMIT 500"
                cur.execute(sql, params)
                rows = cur.fetchall()
        finally:
            conn.close()

        events = []
        for ts, actor, action, obj, ip in rows:
            who = by_uid.get(actor) or by_username.get(actor) or actor
            events.append({
                'timestamp': ts.isoformat() + 'Z' if hasattr(ts, 'isoformat') else str(ts),
                'who': who,
                'action': action,
                'detail': obj,
                'ip_address': ip or '',
            })
        return reply('success', 200, f'{len(events)} event(s)', events)
    return _handle(run)
