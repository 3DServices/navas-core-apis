"""
Driver scoring: the client's scoring rules and the drivers' scorecards.
The arithmetic is in driver_scoring.py; this file reads and writes.

Every route works on the signed-in user's own client (as driver_registry.py
does): another client's rule or driver answers 404.

  GET    /drivers/score/list                  the rules the client is scored
                                              by: its own, and the built-in
                                              default for every violation it
                                              has no rule for (is_default)
  POST   /drivers/score/create                {data:{violation_parameter,
                                              points_denomination,
                                              max_deduction?, score_name?}}
  PUT    /drivers/score/update                {data:{score_uid, ...}}
  DELETE /drivers/score/delete                {data:{score_uid}}: back to the
                                              default for that violation
  GET    /drivers/scorecards?start_date=&end_date=
                                              every driver's scorecard for the
                                              period, ranked (DD-MM-YYYY; the
                                              last 30 days when left out)
  GET    /drivers/registry/<driver_uid>/scorecard?start_date=&end_date=
                                              one driver's, with each violation

These routes were written before but never registered, so they answered 404
and the rules table had no owner; migration 061 gives it one.
"""

import logging
import uuid
from datetime import datetime, timedelta

import psycopg2.errors
from flask import Blueprint, request

from . import driver_scoring as scoring
from .driver_registry import KAMPALA, _audit, _body, _client, _cursor
from .globals import reply, require_auth

driversbp = Blueprint('driversbp', __name__)
log = logging.getLogger('drivers')

_NO_CLIENT = 'Drivers belong to a client account.'
_RULE_NOT_FOUND = 'Scoring rule not found.'
_NEEDS_MIGRATION = ('Scoring rules cannot be saved until the server is updated '
                    '(migration 061). Scorecards use the default rules meanwhile.')
DEFAULT_DAYS = 30
MAX_DAYS = 366

_ALERT_CONDITIONS = ('speed_threshold', 'geofence_breach', 'driver_unauthorised')


# ── helpers ──────────────────────────────────────────────────────────────────

def _rules_ready(cur):
    cur.execute("SELECT COUNT(*) AS n FROM information_schema.columns "
                "WHERE table_name = 'dll_driver_score_configs' "
                "AND column_name IN ('client_uid', 'max_deduction')")
    return cur.fetchone()['n'] == 2


def own_rules(cur, client):
    """The client's stored rules (dicts), [] before migration 061."""
    if not _rules_ready(cur):
        return []
    cur.execute("""SELECT score_uid, score_name, violation_parameter,
                          points_denomination, max_deduction
                     FROM dll_driver_score_configs WHERE client_uid = %s""", (client,))
    return cur.fetchall()


def period(args):
    """(start date, end date) from ?start_date=&end_date= (DD-MM-YYYY), the
    last DEFAULT_DAYS days when left out. Raises ValueError with a message."""
    today = datetime.now(KAMPALA).date()
    raw_start, raw_end = args.get('start_date'), args.get('end_date')
    try:
        end = datetime.strptime(raw_end, '%d-%m-%Y').date() if raw_end else today
        start = (datetime.strptime(raw_start, '%d-%m-%Y').date() if raw_start
                 else end - timedelta(days=DEFAULT_DAYS - 1))
    except ValueError:
        raise ValueError('Invalid date format. Use DD-MM-YYYY')
    if end < start:
        start, end = end, start
    if (end - start).days > MAX_DAYS:
        raise ValueError('Choose at most a year.')
    return start, end


def _vehicle_names(imeis):
    if not imeis:
        return {}
    try:
        from .fuel_registry import _device_names
        return _device_names(sorted(imeis))
    except Exception:                   # noqa: BLE001 -- names are a nicety
        return {i: i for i in imeis}


def load_scorecards(cur, client, start, end, driver_uids=None):
    """Every (or the chosen) driver's scorecard for [start, end], ranked.
    Returns (cards, rules) -- rules are the effective public rules.
    cur is a RealDictCursor; reads only."""
    from . import fuel_rules
    from .fuel_registry import _ISSUE_SELECT

    rules = scoring.effective_rules(own_rules(cur, client))
    by_code = scoring.rules_by_code(rules)

    sql = ("SELECT driver_uid, full_name, status, employee_number "
           "FROM dll_drivers WHERE client_uid = %s")
    args = [client]
    if driver_uids:
        sql += " AND driver_uid = ANY(%s)"
        args.append(list(driver_uids))
    cur.execute(sql, args)
    drivers = cur.fetchall()
    if not drivers:
        return [], rules
    uids = [d['driver_uid'] for d in drivers]
    since = datetime.combine(start, datetime.min.time())
    until = datetime.combine(end + timedelta(days=1), datetime.min.time())

    # Who held which vehicle during the period: says who drove, and who an
    # alert without a recorded driver belongs to.
    cur.execute("""SELECT driver_uid, device_imei, assigned_at, ended_at
                     FROM dll_driver_assignments
                    WHERE client_uid = %s AND assigned_at < %s
                      AND (ended_at IS NULL OR ended_at >= %s)""",
                (client, until, since))
    assignments = cur.fetchall()
    drove = {a['driver_uid'] for a in assignments}

    cur.execute("""SELECT date_triggered, device_imei, device_name, condition,
                          trigger_value, to_jsonb(n) ->> 'driver_uid' AS driver_uid
                     FROM dll_event_notifications n
                    WHERE owner_uid = %s AND condition = ANY(%s)
                      AND date_triggered >= %s AND date_triggered < %s""",
                (client, list(_ALERT_CONDITIONS), since, until))
    alerts = cur.fetchall()

    cur.execute(_ISSUE_SELECT + """ WHERE f.client_uid = %s AND f.driver_uid = ANY(%s)
                                       AND f.voided_at IS NULL
                                       AND f.issued_at >= %s AND f.issued_at < %s""",
                (client, uids, since, until))
    issues = [fuel_rules.public_issue(r) for r in cur.fetchall()]

    imeis = {a['device_imei'] for a in alerts if a.get('device_imei')}
    imeis |= {i['device_imei'] for i in issues if i.get('device_imei')}
    names = _vehicle_names(imeis)

    found = {uid: [] for uid in uids}
    for alert in alerts:
        code = scoring.alert_violation(alert)
        if code is None:
            continue
        uid = alert.get('driver_uid') or scoring.driver_at(
            assignments, alert.get('device_imei'), alert.get('date_triggered'))
        if uid not in found:
            continue
        imei = alert.get('device_imei') or ''
        at = alert.get('date_triggered')
        found[uid].append({
            'code': code, 'label': scoring.VIOLATIONS[code][0],
            'at': at.strftime('%Y-%m-%d %H:%M') if at else '',
            'vehicle': names.get(imei, alert.get('device_name') or imei) if imei else '',
            'detail': str(alert.get('trigger_value') or ''),
        })
    for issue in issues:
        code = scoring.fuel_violation(issue)
        uid = issue.get('driver_uid')
        if code is None or uid not in found:
            continue
        imei = issue.get('device_imei') or ''
        problems = [f.get('message') or f.get('code') for f in issue.get('flags') or ()
                    if f.get('kind') == 'discrepancy']
        found[uid].append({
            'code': code, 'label': scoring.VIOLATIONS[code][0],
            'at': str(issue.get('issued_at') or '').replace('T', ' ')[:16],
            'vehicle': names.get(imei, imei),
            'detail': '; '.join(str(p) for p in problems),
        })

    cards = [scoring.scorecard(d, found[d['driver_uid']], by_code, d['driver_uid'] in drove)
             for d in drivers]
    return scoring.rank(cards), rules


def _period_json(start, end):
    return {'start_date': start.strftime('%d-%m-%Y'), 'end_date': end.strftime('%d-%m-%Y')}


# ── rules ────────────────────────────────────────────────────────────────────

@driversbp.route('/drivers/score/list', methods=['GET'])
@require_auth
def ListScores():
    try:
        with _cursor() as cur:
            client = _client(cur)
            if not client:
                return reply('error', 403, _NO_CLIENT, '')
            rules = scoring.effective_rules(own_rules(cur, client))
        return reply('success', 200, 'Driver scoring rules', rules)
    except Exception:                   # noqa: BLE001
        log.exception('scoring rules list failed')
        return reply('error', 500, 'Could not load the scoring rules.', '')


@driversbp.route('/drivers/score/create', methods=['POST'])
@require_auth
def CreateScore():
    clean, errors = scoring.validate_rule(_body())
    if errors:
        return reply('error', 400, next(iter(errors.values())), {'errors': errors})
    try:
        with _cursor() as cur:
            client = _client(cur)
            if not client:
                return reply('error', 403, _NO_CLIENT, '')
            if not _rules_ready(cur):
                return reply('error', 503, _NEEDS_MIGRATION, '')
            score_uid = str(uuid.uuid4())
            cur.execute(
                """INSERT INTO dll_driver_score_configs
                       (score_uid, score_name, score_order, score_points_order,
                        violation_parameter, points_denomination, max_deduction,
                        client_uid, created_at, updated_at)
                   VALUES (%s, %s, 'highest_best', 'deduct', %s, %s, %s, %s, NOW(), NOW())""",
                (score_uid, clean['score_name'], clean['violation_parameter'],
                 str(clean['points_denomination']), clean['max_deduction'], client))
            rules = scoring.effective_rules(own_rules(cur, client))
        _audit('DRIVER_SCORE_RULE_CREATE', score_uid, client,
               {'violation': clean['violation_parameter'],
                'points': clean['points_denomination']})
        return reply('success', 200, 'Scoring rule saved', rules)
    except psycopg2.errors.UniqueViolation:
        return reply('error', 409, 'You already have a rule for this violation. '
                                   'Edit it instead.', '')
    except Exception:                   # noqa: BLE001
        log.exception('scoring rule create failed')
        return reply('error', 500, 'Could not save the scoring rule.', '')


@driversbp.route('/drivers/score/update', methods=['PUT'])
@require_auth
def UpdateScore():
    data = _body()
    score_uid = str(data.get('score_uid') or '').strip()
    if not score_uid or score_uid.startswith('default:'):
        return reply('error', 400, 'Choose one of your own rules to edit; to change '
                                   'a default, create a rule for that violation.', '')
    clean, errors = scoring.validate_rule(data)
    if errors:
        return reply('error', 400, next(iter(errors.values())), {'errors': errors})
    try:
        with _cursor() as cur:
            client = _client(cur)
            if not client:
                return reply('error', 403, _NO_CLIENT, '')
            if not _rules_ready(cur):
                return reply('error', 503, _NEEDS_MIGRATION, '')
            cur.execute(
                """UPDATE dll_driver_score_configs
                      SET score_name = %s, violation_parameter = %s,
                          points_denomination = %s, max_deduction = %s,
                          updated_at = NOW()
                    WHERE score_uid = %s AND client_uid = %s""",
                (clean['score_name'], clean['violation_parameter'],
                 str(clean['points_denomination']), clean['max_deduction'],
                 score_uid, client))
            if cur.rowcount == 0:
                return reply('error', 404, _RULE_NOT_FOUND, '')
            rules = scoring.effective_rules(own_rules(cur, client))
        _audit('DRIVER_SCORE_RULE_EDIT', score_uid, client,
               {'violation': clean['violation_parameter'],
                'points': clean['points_denomination']})
        return reply('success', 200, 'Scoring rule updated', rules)
    except psycopg2.errors.UniqueViolation:
        return reply('error', 409, 'You already have a rule for this violation.', '')
    except Exception:                   # noqa: BLE001
        log.exception('scoring rule update failed')
        return reply('error', 500, 'Could not update the scoring rule.', '')


@driversbp.route('/drivers/score/delete', methods=['DELETE'])
@require_auth
def DeleteScore():
    data = _body()
    score_uid = str(data.get('score_uid') or request.args.get('score_uid') or '').strip()
    if not score_uid or score_uid.startswith('default:'):
        return reply('error', 400, 'Default rules cannot be deleted; set its points '
                                   'to 0 to stop counting that violation.', '')
    try:
        with _cursor() as cur:
            client = _client(cur)
            if not client:
                return reply('error', 403, _NO_CLIENT, '')
            if not _rules_ready(cur):
                return reply('error', 503, _NEEDS_MIGRATION, '')
            cur.execute("DELETE FROM dll_driver_score_configs "
                        "WHERE score_uid = %s AND client_uid = %s", (score_uid, client))
            if cur.rowcount == 0:
                return reply('error', 404, _RULE_NOT_FOUND, '')
            rules = scoring.effective_rules(own_rules(cur, client))
        _audit('DRIVER_SCORE_RULE_DELETE', score_uid, client)
        return reply('success', 200, 'Scoring rule removed; the default applies again',
                     rules)
    except Exception:                   # noqa: BLE001
        log.exception('scoring rule delete failed')
        return reply('error', 500, 'Could not delete the scoring rule.', '')


# ── scorecards ───────────────────────────────────────────────────────────────

def _summary(card):
    """A scorecard without its violation list, for the ranking."""
    return {k: v for k, v in card.items() if k != 'violations'}


@driversbp.route('/drivers/scorecards', methods=['GET'])
@require_auth
def Scorecards():
    try:
        start, end = period(request.args)
    except ValueError as error:
        return reply('error', 400, str(error), '')
    try:
        with _cursor() as cur:
            client = _client(cur)
            if not client:
                return reply('error', 403, _NO_CLIENT, '')
            cards, rules = load_scorecards(cur, client, start, end)
        return reply('success', 200, 'Driver scorecards', {
            **_period_json(start, end),
            'start_score': scoring.START,
            'rules': rules,
            'drivers': [_summary(c) for c in cards],
        })
    except Exception:                   # noqa: BLE001
        log.exception('scorecards failed')
        return reply('error', 500, 'Could not load the scorecards.', '')


@driversbp.route('/drivers/registry/<driver_uid>/scorecard', methods=['GET'])
@require_auth
def DriverScorecard(driver_uid):
    try:
        start, end = period(request.args)
    except ValueError as error:
        return reply('error', 400, str(error), '')
    try:
        with _cursor() as cur:
            client = _client(cur)
            if not client:
                return reply('error', 403, _NO_CLIENT, '')
            # Ranked among all the client's drivers, so the card says where
            # this driver stands.
            cards, rules = load_scorecards(cur, client, start, end)
        card = next((c for c in cards if c['driver_uid'] == driver_uid), None)
        if card is None:
            return reply('error', 404, 'Driver not found.', '')
        scored = sum(1 for c in cards if c['score'] is not None)
        return reply('success', 200, 'Driver scorecard', {
            **_period_json(start, end),
            'start_score': scoring.START,
            'rules': rules,
            'ranked_drivers': scored,
            **card,
        })
    except Exception:                   # noqa: BLE001
        log.exception('driver scorecard failed')
        return reply('error', 500, 'Could not load the scorecard.', '')
