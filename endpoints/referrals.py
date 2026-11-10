"""
Refer & Earn (migration 050). Rules in referral_rules.py.

  GET  /referrals/me                      your code, who joined with it, hours
                                          earned, and whether you may still
                                          enter a code yourself
  POST /referrals/claim                   {data:{code}} -- the new customer
                                          enters a referrer's code
  GET  /referrals/admin/list?status=      staff: every referral
  POST /referrals/admin/<id>/reward       staff: pay a held ('qualified') one
  POST /referrals/admin/<id>/reject       staff: {data:{note}}

The reward itself is paid by on_paid_top_up(), which the mobile-money webhook
(finance.py, POST /payments/transactions/notifications) calls once it has
credited a successful payment. It adds one pack of the token named by
REFERRAL_REWARD_TOKEN_ID (a 24-hour token in dll_tokens_registry) to the
referrer's wallet, exactly as a purchase adds one. When that is not set the
referral is held as 'qualified', not lost.
"""

import logging
import uuid
from contextlib import contextmanager

import psycopg2.errors
from flask import Blueprint, g, request

from . import db_pool, referral_rules as rules
from .globals import (log_audit_event, reply, require_auth, require_staff,
                      resolve_client_account, resolve_wallet_owner)
from .notifier import notify

referrals_bp = Blueprint('referrals', __name__)
log = logging.getLogger('referrals')

_NOT_ENABLED = 'Referrals are not enabled on this server yet'
_PAID = ('successful', 'success')


@contextmanager
def _cursor():
    connection = db_pool.connect()
    try:
        with connection:
            with connection.cursor() as cursor:
                yield cursor
    finally:
        connection.close()               # back to the pool


def _reward_token_id():
    from config import REFERRAL_REWARD_TOKEN_ID
    return REFERRAL_REWARD_TOKEN_ID


def _client(cursor):
    """The signed-in user's company, or None for a login with no client."""
    return resolve_client_account(cursor, g.current_user['account_uid'])


def _company(cursor, client_uid):
    cursor.execute(
        "SELECT to_jsonb(c)->>'client_name', to_jsonb(c)->>'client_email' "
        "FROM dll_client_accounts c WHERE client_uid = %s", (client_uid,))
    row = cursor.fetchone()
    return (row[0] or '', row[1] or '') if row else ('', '')


def _code_for(cursor, client_uid):
    cursor.execute("SELECT code FROM dll_referral_codes WHERE client_uid = %s",
                   (client_uid,))
    row = cursor.fetchone()
    if row:
        return row[0]
    for _ in range(5):                    # a clash is ~1 in 28 million
        cursor.execute(
            "INSERT INTO dll_referral_codes (client_uid, code) VALUES (%s, %s) "
            "ON CONFLICT DO NOTHING", (client_uid, rules.make_code()))
        cursor.execute("SELECT code FROM dll_referral_codes WHERE client_uid = %s",
                       (client_uid,))
        row = cursor.fetchone()
        if row:
            return row[0]
    raise RuntimeError('could not make a referral code')


def _has_paid_top_up(cursor, client_uid):
    _, owners = resolve_wallet_owner(cursor, client_uid)
    cursor.execute(
        "SELECT 1 FROM dll_payment_logs WHERE payment_account = ANY(%s) "
        "AND LOWER(payment_status) = ANY(%s) LIMIT 1", (owners, list(_PAID)))
    return cursor.fetchone() is not None


def _credit(cursor, referral_id, referrer, token_id):
    """One reward pack into the referrer's wallet; marks the referral
    rewarded. Returns the new token_billing_uid, or None if the token is
    not in the registry."""
    cursor.execute("SELECT billing_unit FROM dll_tokens_registry WHERE token_id = %s",
                   (token_id,))
    row = cursor.fetchone()
    if row is None:
        return None
    billing_uid = str(uuid.uuid4())
    # The same row a purchase writes (finance.py, TransactionUpdate).
    cursor.execute(
        "INSERT INTO dll_user_token_accounts (client_uid, token_balance, token_status, "
        "token_hours_used, token_hours_left, token_billing_uid) "
        "VALUES (%s, %s, %s, %s, %s, %s)",
        (referrer, token_id, 'active', 0, row[0], billing_uid))
    cursor.execute(
        "UPDATE dll_referrals SET status = 'rewarded', note = NULL, "
        "reward_token_uid = %s, rewarded_at = NOW(), "
        "qualified_at = COALESCE(qualified_at, NOW()) WHERE id = %s",
        (billing_uid, referral_id))
    notify(cursor, referrer, 'You earned %d free hours' % rules.REWARD_HOURS,
           'A company you referred made its first top-up. %d hours have been '
           'added to your token wallet.' % rules.REWARD_HOURS,
           'referral', 'in_app')
    return billing_uid


def on_paid_top_up(cursor, client_uid, payment_ref):
    """Called by the payment webhook after a successful payment for
    client_uid has been credited, inside its transaction. Pays (or holds) the
    reward of whoever referred client_uid. Never raises: a referral problem
    must not undo a customer's top-up."""
    cursor.execute("SAVEPOINT referral_reward")
    try:
        cursor.execute(
            "SELECT id, referrer_client_uid FROM dll_referrals "
            "WHERE referee_client_uid = %s AND status = 'pending' FOR UPDATE",
            (client_uid,))
        row = cursor.fetchone()
        if row is None:
            cursor.execute("RELEASE SAVEPOINT referral_reward")
            return
        referral_id, referrer = row
        cursor.execute(
            "SELECT COUNT(*) FROM dll_referrals WHERE referrer_client_uid = %s "
            "AND status = 'rewarded' "
            "AND rewarded_at >= date_trunc('month', NOW())", (referrer,))
        this_month = cursor.fetchone()[0]
        token_id = _reward_token_id()
        status, note = rules.reward_decision(this_month, bool(token_id))
        cursor.execute(
            "UPDATE dll_referrals SET status = 'qualified', qualified_at = NOW(), "
            "qualifying_payment = %s, note = %s WHERE id = %s",
            (payment_ref, note, referral_id))
        reward_uid = None
        if status == 'rewarded':
            reward_uid = _credit(cursor, referral_id, referrer, token_id)
            if reward_uid is None:
                cursor.execute(
                    "UPDATE dll_referrals SET note = %s WHERE id = %s",
                    ('The referral reward token is not in the token registry.',
                     referral_id))
        cursor.execute("RELEASE SAVEPOINT referral_reward")
    except Exception as error:
        cursor.execute("ROLLBACK TO SAVEPOINT referral_reward")
        if not isinstance(error, psycopg2.errors.UndefinedTable):
            log.exception('referral reward for %s failed', client_uid)
        return
    try:
        log_audit_event(actor='system', action='REFERRAL_REWARD' if reward_uid
                        else 'REFERRAL_QUALIFIED',
                        obj=f'referral:{referral_id}', domain='TOKEN',
                        meta={'referrer': referrer, 'referee': client_uid,
                              'payment': payment_ref, 'reward_token': reward_uid})
    except Exception:
        log.exception('referral audit failed')


@referrals_bp.route('/referrals/me', methods=['GET'])
@require_auth
def my_referrals():
    try:
        with _cursor() as cursor:
            client = _client(cursor)
            if client is None:
                return reply('error', 403,
                             'Refer & Earn is for customer accounts.', '')
            code = _code_for(cursor, client)
            cursor.execute(
                "SELECT r.status, r.claimed_at, r.rewarded_at, "
                "to_jsonb(c)->>'client_name' FROM dll_referrals r "
                "LEFT JOIN dll_client_accounts c "
                "ON c.client_uid = r.referee_client_uid "
                "WHERE r.referrer_client_uid = %s ORDER BY r.claimed_at DESC",
                (client,))
            rows = [{'status': r[0],
                     'claimed_at': r[1].isoformat() if r[1] else None,
                     'rewarded_at': r[2].isoformat() if r[2] else None,
                     'name': rules.masked_name(r[3])}
                    for r in cursor.fetchall()]
            cursor.execute(
                "SELECT code, status FROM dll_referrals "
                "WHERE referee_client_uid = %s", (client,))
            mine = cursor.fetchone()
            can_enter = mine is None and not _has_paid_top_up(cursor, client)
        return reply('success', 200, 'Referrals', {
            'code': code,
            'reward_hours': rules.REWARD_HOURS,
            'share_text': rules.share_text(code),
            **rules.summary(rows),
            'referrals': [r for r in rows if r['status'] != 'rejected'][:50],
            'referred_by': {'code': mine[0], 'status': mine[1]} if mine else None,
            'can_enter_code': can_enter,
        })
    except psycopg2.errors.UndefinedTable:
        return reply('error', 503, _NOT_ENABLED, '')
    except Exception as error:
        log.exception('referrals/me failed')
        return reply('error', 500, str(error), '')


@referrals_bp.route('/referrals/claim', methods=['POST'])
@require_auth
def claim():
    data = (request.get_json(silent=True) or {}).get('data') or {}
    try:
        code = rules.normalize_code(data.get('code'))
    except rules.ReferralError as error:
        return reply('error', 400, str(error), '')
    try:
        with _cursor() as cursor:
            client = _client(cursor)
            if client is None:
                return reply('error', 403,
                             'Refer & Earn is for customer accounts.', '')
            cursor.execute(
                "SELECT client_uid FROM dll_referral_codes WHERE code = %s", (code,))
            row = cursor.fetchone()
            referrer = row[0] if row else None
            cursor.execute(
                "SELECT 1 FROM dll_referrals WHERE referee_client_uid = %s", (client,))
            already = cursor.fetchone() is not None
            problem = rules.claim_problem(
                client, referrer,
                _company(cursor, client)[1],
                _company(cursor, referrer)[1] if referrer else '',
                already_referred=already,
                has_paid_top_up=_has_paid_top_up(cursor, client))
            if problem:
                return reply('error', 409 if already else 400, problem, '')
            cursor.execute(
                "INSERT INTO dll_referrals (referrer_client_uid, referee_client_uid, "
                "code, claimed_by) VALUES (%s, %s, %s, %s) "
                "ON CONFLICT (referee_client_uid) DO NOTHING",
                (referrer, client, code, g.current_user['account_uid']))
            if cursor.rowcount == 0:
                return reply('error', 409,
                             'Your account has already used a referral code.', '')
            notify(cursor, referrer, 'A friend used your referral code',
                   '%s joined with your code. You get %d free hours when '
                   'they make their first top-up.'
                   % (rules.masked_name(_company(cursor, client)[0]),
                      rules.REWARD_HOURS),
                   'referral', 'in_app')
        log_audit_event(actor=g.current_user['account_uid'], action='REFERRAL_CLAIM',
                        obj=f'client:{client}', domain='CLIENT',
                        meta={'referrer': referrer, 'code': code})
        return reply('success', 200,
                     'Code accepted. Your friend gets %d free hours after your '
                     'first top-up.' % rules.REWARD_HOURS,
                     {'code': code, 'status': 'pending'})
    except psycopg2.errors.UndefinedTable:
        return reply('error', 503, _NOT_ENABLED, '')
    except Exception as error:
        log.exception('referrals/claim failed')
        return reply('error', 500, str(error), '')


@referrals_bp.route('/referrals/admin/list', methods=['GET'])
@require_staff()
def admin_list():
    status = request.args.get('status')
    sql = ("SELECT r.id, r.referrer_client_uid, to_jsonb(a)->>'client_name', "
           "r.referee_client_uid, to_jsonb(b)->>'client_name', r.code, r.status, "
           "r.note, r.qualifying_payment, r.reward_token_uid, r.claimed_at, "
           "r.qualified_at, r.rewarded_at FROM dll_referrals r "
           "LEFT JOIN dll_client_accounts a ON a.client_uid = r.referrer_client_uid "
           "LEFT JOIN dll_client_accounts b ON b.client_uid = r.referee_client_uid")
    params = ()
    if status in rules.STATUSES:
        sql += " WHERE r.status = %s"
        params = (status,)
    sql += " ORDER BY r.claimed_at DESC LIMIT 500"
    keys = ('id', 'referrer_client_uid', 'referrer_name', 'referee_client_uid',
            'referee_name', 'code', 'status', 'note', 'qualifying_payment',
            'reward_token_uid', 'claimed_at', 'qualified_at', 'rewarded_at')
    try:
        with _cursor() as cursor:
            cursor.execute(sql, params)
            rows = [{k: (v.isoformat() if hasattr(v, 'isoformat') else v)
                     for k, v in zip(keys, r)} for r in cursor.fetchall()]
        return reply('success', 200, 'Referrals', rows)
    except psycopg2.errors.UndefinedTable:
        return reply('error', 503, _NOT_ENABLED, '')
    except Exception as error:
        return reply('error', 500, str(error), '')


def _held(cursor, referral_id):
    cursor.execute("SELECT referrer_client_uid, status FROM dll_referrals "
                   "WHERE id = %s FOR UPDATE", (referral_id,))
    return cursor.fetchone()


@referrals_bp.route('/referrals/admin/<int:referral_id>/reward', methods=['POST'])
@require_staff()
def admin_reward(referral_id):
    token_id = _reward_token_id()
    if not token_id:
        return reply('error', 409, 'Set REFERRAL_REWARD_TOKEN_ID first.', '')
    try:
        with _cursor() as cursor:
            row = _held(cursor, referral_id)
            if row is None:
                return reply('error', 404, 'No such referral.', '')
            if row[1] != 'qualified':
                return reply('error', 409,
                             'Only a qualified referral can be paid; this one is %s.'
                             % row[1], '')
            reward_uid = _credit(cursor, referral_id, row[0], token_id)
            if reward_uid is None:
                return reply('error', 409,
                             'REFERRAL_REWARD_TOKEN_ID is not in the token registry.', '')
        log_audit_event(actor=g.current_user['account_uid'], action='REFERRAL_REWARD',
                        obj=f'referral:{referral_id}', domain='TOKEN',
                        meta={'referrer': row[0], 'reward_token': reward_uid})
        return reply('success', 200, 'Reward paid',
                     {'id': referral_id, 'reward_token_uid': reward_uid})
    except psycopg2.errors.UndefinedTable:
        return reply('error', 503, _NOT_ENABLED, '')
    except Exception as error:
        return reply('error', 500, str(error), '')


@referrals_bp.route('/referrals/admin/<int:referral_id>/reject', methods=['POST'])
@require_staff()
def admin_reject(referral_id):
    data = (request.get_json(silent=True) or {}).get('data') or {}
    note = str(data.get('note') or '').strip()[:500] or 'Rejected by staff.'
    try:
        with _cursor() as cursor:
            row = _held(cursor, referral_id)
            if row is None:
                return reply('error', 404, 'No such referral.', '')
            if row[1] not in ('pending', 'qualified'):
                return reply('error', 409,
                             'This referral is already %s.' % row[1], '')
            cursor.execute("UPDATE dll_referrals SET status = 'rejected', note = %s "
                           "WHERE id = %s", (note, referral_id))
        log_audit_event(actor=g.current_user['account_uid'], action='REFERRAL_REJECT',
                        obj=f'referral:{referral_id}', domain='CLIENT',
                        meta={'note': note})
        return reply('success', 200, 'Referral rejected', {'id': referral_id})
    except psycopg2.errors.UndefinedTable:
        return reply('error', 503, _NOT_ENABLED, '')
    except Exception as error:
        return reply('error', 500, str(error), '')
