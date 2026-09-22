"""
waswa_gating.py — is this action Waswa's to take, and if not, whose?

Reads dll_waswa_gated_actions (migration 033). Phase 8 wires this into the
proposal and approval flow; it is here now so the rules live in one place from
the start rather than being reinvented when that phase arrives.

The default is the safe one. An action nobody has classified is treated as
gated with no approver — Waswa proposes it and says plainly that it needs
approval it cannot route yet. An unknown action is never assumed to be
harmless, because the cost of that assumption is a device command or a billing
change taken on a model's judgement.
"""

import psycopg2
from flask import current_app


def _connect():
    return psycopg2.connect(current_app.config['db_link'])


def check(action_key, country=None):
    """How Waswa must handle [action_key].

    Returns:
        may_act        True only for Level 0 actions.
        approval_level 0-3, or None when nobody has classified it.
        approver_role  who signs it off, or None when nobody is named.
        routable       True when there is someone to send the proposal to.
        reason         one line for the transparency log.
    """
    result = {
        'action_key': action_key,
        'may_act': False,
        'approval_level': None,
        'approver_role': None,
        'routable': False,
        'threshold_kind': None,
        'threshold_value': None,
        'source_ref': None,
        'reason': 'action not classified — treated as gated',
    }

    conn = None
    try:
        conn = _connect()
        with conn:
            with conn.cursor() as cur:
                # A country-specific row wins over the general one.
                cur.execute(
                    "SELECT approval_level, approver_role, waswa_may_act, "
                    "       threshold_kind, threshold_value, threshold_note, "
                    "       source_ref "
                    "FROM dll_waswa_gated_actions "
                    "WHERE action_key = %s AND active = TRUE "
                    "  AND (country_scope IS NULL OR country_scope = %s) "
                    "ORDER BY country_scope NULLS LAST LIMIT 1",
                    (str(action_key), country),
                )
                row = cur.fetchone() if cur.rowcount else None
    except psycopg2.Error as error:
        result['reason'] = f'gating table unavailable ({error}) — treated as gated'
        return result
    finally:
        if conn:
            conn.close()

    if not row:
        return result

    (level, approver, may_act, threshold_kind, threshold_value,
     threshold_note, source_ref) = row

    result.update({
        'approval_level': level,
        'approver_role': approver,
        'may_act': bool(may_act),
        'threshold_kind': threshold_kind,
        'threshold_value': float(threshold_value) if threshold_value is not None else None,
        'source_ref': source_ref,
        'routable': approver is not None,
    })

    if result['may_act']:
        result['reason'] = 'Level 0 — automated, no approval needed'
    elif approver:
        result['reason'] = f'needs approval from {approver} (level {level})'
    else:
        result['reason'] = 'gated, but no approver role has been named yet'

    if threshold_kind and threshold_value is None:
        result['reason'] += f'; {threshold_kind} threshold not set'
        if threshold_note:
            result['threshold_note'] = threshold_note

    return result


def unassigned():
    """Gated actions still missing an approver or a threshold.

    The admin surface reads this; it is the list of business decisions
    blocking the approval flow.
    """
    conn = None
    try:
        conn = _connect()
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT action_key, description, source_ref, "
                    "       approver_gap, threshold_gap "
                    "FROM vw_waswa_unassigned_approvals ORDER BY action_key")
                rows = cur.fetchall() if cur.rowcount > 0 else []
        return [
            {'action_key': r[0], 'description': r[1], 'source_ref': r[2],
             'approver_gap': r[3], 'threshold_gap': r[4]}
            for r in rows
        ]
    except psycopg2.Error:
        return []
    finally:
        if conn:
            conn.close()
