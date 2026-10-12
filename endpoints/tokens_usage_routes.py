"""
Daily token usage (migration 049).

  GET  /tokens/<client_uid>/usage/daily?days=14
       usage per day and per service for one wallet. Takes that wallet's
       reading for today first, so today is always current.
  POST /tokens/usage/snapshot/run
       takes today's reading for every wallet. Staff only. Schedule it once a
       day close to midnight (Africa/Kampala), so each day's reading is taken
       at its end even for wallets nobody looked at.

The arithmetic is in token_usage.py.
"""

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import psycopg2.errors
from flask import Blueprint, request

from . import db_pool, token_usage
from .globals import reply, require_permission, require_staff, resolve_wallet_owner

token_usage_bp = Blueprint('token_usage', __name__)
log = logging.getLogger('token_usage')

_KLA = ZoneInfo('Africa/Kampala')
DEFAULT_DAYS = 14
_NOT_ENABLED = 'Daily token usage is not enabled on this server yet'


def _today():
    return datetime.now(_KLA).date()


def _snapshot(cursor, owner_uids=None):
    """Write today's reading for the token accounts of owner_uids (every
    account when None). Returns how many were written."""
    sql = ("SELECT client_uid, token_billing_uid, token_balance, token_used_units, "
           "token_units_left, token_hours_used, token_hours_left "
           "FROM dll_user_token_accounts WHERE COALESCE(token_billing_uid, '') <> ''")
    params = ()
    if owner_uids is not None:
        sql += " AND client_uid = ANY(%s)"
        params = (list(owner_uids),)
    cursor.execute(sql, params)
    columns = [d[0] for d in cursor.description]
    accounts = [dict(zip(columns, row)) for row in cursor.fetchall()]
    if not accounts:
        return 0

    # Service name and billing unit per token, two queries in all.
    token_ids = list({a['token_balance'] for a in accounts if a.get('token_balance')})
    tokens = {}
    if token_ids:
        cursor.execute(
            "SELECT t.token_id, p.product_name, t.billing_unit "
            "FROM dll_tokens_registry t "
            "LEFT JOIN abi_products_manager p ON p.product_uid = t.token_product_uid "
            "WHERE t.token_id = ANY(%s)", (token_ids,))
        tokens = {r[0]: (r[1], r[2]) for r in cursor.fetchall()}

    today = _today()
    written = 0
    for account in accounts:
        used, left = token_usage.reading(account)
        if used is None:
            continue                    # awaiting first use, or unreadable
        service, unit = tokens.get(account.get('token_balance'), (None, None))
        cursor.execute(
            "INSERT INTO dll_token_usage_daily (client_uid, token_billing_uid, day, "
            "service, billing_unit, used_total, left_total, recorded_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, NOW()) "
            "ON CONFLICT (client_uid, token_billing_uid, day) DO UPDATE SET "
            "service = EXCLUDED.service, billing_unit = EXCLUDED.billing_unit, "
            "used_total = EXCLUDED.used_total, left_total = EXCLUDED.left_total, "
            "recorded_at = NOW()",
            (str(account['client_uid']), str(account['token_billing_uid']), today,
             service or 'Other', unit or 'unit', used, left))
        written += 1
    return written


@token_usage_bp.route('/tokens/<string:client_uid>/usage/daily', methods=['GET'])
@require_permission('tokens.view_balance')
def daily_usage(client_uid):
    try:
        days = int(request.args.get('days', DEFAULT_DAYS))
    except ValueError:
        return reply('error', 400, 'days must be a number', '')
    days = max(1, min(days, token_usage.MAX_DAYS))
    today = _today()

    try:
        connection = db_pool.connect()
        try:
            with connection:
                with connection.cursor() as cursor:
                    wallet, owner_uids = resolve_wallet_owner(cursor, client_uid)
                    _snapshot(cursor, owner_uids)
                    cursor.execute(
                        "SELECT token_billing_uid, service, billing_unit, day, used_total "
                        "FROM dll_token_usage_daily "
                        "WHERE client_uid = ANY(%s) AND day >= %s",
                        (list(owner_uids), today - timedelta(days=days)))
                    snapshots = [{'account': r[0], 'service': r[1], 'unit': r[2],
                                  'day': r[3], 'used': r[4]} for r in cursor.fetchall()]
                    cursor.execute(
                        "SELECT MIN(day) FROM dll_token_usage_daily "
                        "WHERE client_uid = ANY(%s)", (list(owner_uids),))
                    first = cursor.fetchone()[0]
        finally:
            connection.close()
    except psycopg2.errors.UndefinedTable:
        return reply('error', 503, _NOT_ENABLED, '')
    except Exception as error:
        log.exception('daily token usage failed: %s', error)
        return reply('error', 500, 'Could not read token usage', '')

    result = token_usage.daily(snapshots, today, days)
    return reply('success', 200, 'Daily token usage', {
        'client_uid': wallet,
        'today': today.isoformat(),
        'history_since': first.isoformat() if first else None,
        'days': [{'day': d['day'].isoformat(),
                  'by_service': {k: round(v, 2) for k, v in d['by_service'].items()},
                  'unknown': d['unknown']} for d in result['days']],
        'services': result['services'],
        'units': result['units'],
    })


@token_usage_bp.route('/tokens/usage/snapshot/run', methods=['POST'])
@require_staff()
def snapshot_run():
    try:
        connection = db_pool.connect()
        try:
            with connection:
                with connection.cursor() as cursor:
                    written = _snapshot(cursor)
        finally:
            connection.close()
    except psycopg2.errors.UndefinedTable:
        return reply('error', 503, _NOT_ENABLED, '')
    except Exception as error:
        log.exception('token usage snapshot failed: %s', error)
        return reply('error', 500, 'Could not record token usage', '')
    return reply('success', 200, 'Token usage recorded',
                 {'day': _today().isoformat(), 'accounts': written})
