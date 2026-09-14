"""
pause.py — Unit-level pause of token burn.

Moves "pause on low balance" from a fleet-account switch to per-unit / per-group
control:

  * POST   /pause/action            — pause/resume specific units or groups now
  * GET    /pause/rules/<owner>     — list auto-pause rules
  * POST   /pause/rules             — create/update an auto-pause rule
                                      (mode 'until' = pause now, resume at a time;
                                       mode 'balance' = auto-pause below a balance)
  * DELETE /pause/rules/<rule_id>   — remove a rule
  * POST   /pause/rules/run         — enforce rules (worker/cron); dry-run aware
  * GET    /pause/analytics/<owner> — product-owner analytics on pause behaviour

Every pause/resume is logged to dll_pause_events for analytics.
"""

import json
from datetime import datetime

import psycopg2
from flask import Blueprint, current_app, request

from .globals import reply

pause_bp = Blueprint("Pause", __name__)


# ── Helpers ─────────────────────────────────────────────────────────────────

def _conn():
    return psycopg2.connect(current_app.config["db_link"])


def _client_balance(cur, owner_uid):
    """Token balance used by balance-based rules and logged with each event.
    Defined as the count of the client's active token accounts."""
    cur.execute(
        "SELECT COUNT(*) FROM dll_user_token_accounts "
        "WHERE client_uid=%s AND token_status='active'",
        (str(owner_uid),),
    )
    row = cur.fetchone()
    return int(row[0]) if row and row[0] is not None else 0


def _group_devices(cur, group_uid):
    """IMEIs attached to a device group (dll_device_groups.devices_attached)."""
    cur.execute(
        "SELECT devices_attached FROM dll_device_groups WHERE group_local_uid=%s",
        (str(group_uid),),
    )
    row = cur.fetchone()
    if not row or not row[0]:
        return []
    try:
        return list(json.loads(row[0]))
    except Exception:
        return []


def _expand(cur, scope, target):
    """Resolve a target into a list of device IMEIs."""
    if scope == "group":
        return _group_devices(cur, target)
    return [target]


def _set_pause(cur, imei, action):
    """Apply pause/resume to one device. Returns True if the state changed."""
    cur.execute(
        "SELECT subscription_status FROM dll_device_subscriptions "
        "WHERE device_imei_number=%s",
        (str(imei),),
    )
    if cur.rowcount < 1:
        return False
    status = cur.fetchone()[0]
    if action == "pause" and status == "active":
        cur.execute(
            "UPDATE dll_device_subscriptions SET subscription_status='paused' "
            "WHERE device_imei_number=%s",
            (str(imei),),
        )
        return True
    if action == "resume" and status == "paused":
        cur.execute(
            "UPDATE dll_device_subscriptions SET subscription_status='active' "
            "WHERE device_imei_number=%s",
            (str(imei),),
        )
        return True
    return False


def _log_event(cur, owner_uid, imei, group_uid, action, reason, balance, source):
    try:
        cur.execute(
            """
            INSERT INTO dll_pause_events
                (owner_uid, device_imei, group_uid, action, reason,
                 balance_at_event, source)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (str(owner_uid), imei, group_uid, action, reason, balance, source),
        )
    except Exception as e:  # pragma: no cover
        print(f"[pause] log failed: {e}")


# ── Manual pause / resume ────────────────────────────────────────────────────

@pause_bp.route("/pause/action", methods=["POST"])
def PauseAction():
    """Pause or resume specific units and/or groups immediately."""
    try:
        payload = request.get_json(silent=True) or {}
        data = payload.get("data") or {}
        owner_uid = str(data.get("owner_uid", "")).strip()
        action = str(data.get("action", "")).strip().lower()
        reason = str(data.get("reason", "manual")).strip() or "manual"
        targets = data.get("targets") or []

        if len(owner_uid) < 5 or action not in ("pause", "resume") or not targets:
            return reply("error", 400, "owner_uid, action and targets are required", "")

        changed, skipped = 0, 0
        conn = _conn()
        with conn:
            with conn.cursor() as cur:
                balance = _client_balance(cur, owner_uid)
                for t in targets:
                    scope = str(t.get("scope", "device"))
                    target = str(t.get("target", ""))
                    if not target:
                        continue
                    group_uid = target if scope == "group" else None
                    for imei in _expand(cur, scope, target):
                        if _set_pause(cur, imei, action):
                            changed += 1
                            _log_event(cur, owner_uid, imei, group_uid, action,
                                       reason, balance, "user")
                        else:
                            skipped += 1
        conn.close()
        return reply("success", 200,
                     f"{action.title()}d {changed} unit(s)",
                     {"changed": changed, "skipped": skipped})
    except Exception as error:
        return reply("error", 500, str(error), "")


# ── Auto-pause rules ─────────────────────────────────────────────────────────

@pause_bp.route("/pause/rules/<owner_uid>", methods=["GET"])
def ListPauseRules(owner_uid):
    try:
        conn = _conn()
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, scope, target_uid, mode, resume_at, "
                    "balance_threshold, active FROM dll_pause_rules "
                    "WHERE owner_uid=%s ORDER BY created_at DESC",
                    (str(owner_uid),),
                )
                rules = [{
                    "id": r[0], "scope": r[1], "target_uid": r[2], "mode": r[3],
                    "resume_at": r[4].isoformat() if r[4] else "",
                    "balance_threshold": float(r[5]) if r[5] is not None else None,
                    "active": r[6],
                } for r in cur.fetchall()]
        conn.close()
        return reply("success", 200, "Pause rules", rules)
    except Exception as error:
        return reply("error", 500, str(error), "")


@pause_bp.route("/pause/rules", methods=["POST"])
def SavePauseRule():
    """Create/update a rule. mode='until' also pauses the target immediately."""
    try:
        payload = request.get_json(silent=True) or {}
        data = payload.get("data") or {}
        owner_uid = str(data.get("owner_uid", "")).strip()
        scope = str(data.get("scope", "device")).strip()
        target = str(data.get("target", "")).strip()
        mode = str(data.get("mode", "")).strip().lower()
        active = bool(data.get("active", True))

        if len(owner_uid) < 5 or not target or mode not in ("until", "balance"):
            return reply("error", 400, "owner_uid, target and a valid mode are required", "")

        resume_at = None
        threshold = None
        if mode == "until":
            raw = str(data.get("resume_at", "")).strip()
            if not raw:
                return reply("error", 400, "resume_at is required for a timed pause", "")
            try:
                resume_at = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except ValueError:
                return reply("error", 400, "resume_at must be ISO-8601", "")
        else:
            try:
                threshold = float(data.get("balance_threshold"))
            except (TypeError, ValueError):
                return reply("error", 400, "balance_threshold is required", "")

        conn = _conn()
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO dll_pause_rules
                        (owner_uid, scope, target_uid, mode, resume_at,
                         balance_threshold, active, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (owner_uid, scope, target_uid) DO UPDATE SET
                        mode              = EXCLUDED.mode,
                        resume_at         = EXCLUDED.resume_at,
                        balance_threshold = EXCLUDED.balance_threshold,
                        active            = EXCLUDED.active,
                        updated_at        = NOW()
                    """,
                    (owner_uid, scope, target, mode, resume_at, threshold, active),
                )
                # A timed pause takes effect now.
                if mode == "until" and active:
                    balance = _client_balance(cur, owner_uid)
                    group_uid = target if scope == "group" else None
                    for imei in _expand(cur, scope, target):
                        if _set_pause(cur, imei, "pause"):
                            _log_event(cur, owner_uid, imei, group_uid, "pause",
                                       "scheduled_until", balance, "user")
        conn.close()
        return reply("success", 200, "Pause rule saved", "")
    except Exception as error:
        return reply("error", 500, str(error), "")


@pause_bp.route("/pause/rules/<int:rule_id>", methods=["DELETE"])
def DeletePauseRule(rule_id):
    try:
        conn = _conn()
        with conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM dll_pause_rules WHERE id=%s", (rule_id,))
                gone = cur.rowcount
        conn.close()
        if gone == 0:
            return reply("error", 404, "Rule not found", "")
        return reply("success", 200, "Pause rule removed", "")
    except Exception as error:
        return reply("error", 500, str(error), "")


@pause_bp.route("/pause/rules/run", methods=["POST"])
def RunPauseRules():
    """Enforce auto-pause rules. Safe to call from a scheduler.

    * 'until' rules whose resume_at has passed → resume + deactivate.
    * 'balance' rules where balance <= threshold → pause active units.
    Pass {"data": {"live": true}} to apply; otherwise dry-run (no changes).
    """
    try:
        payload = request.get_json(silent=True) or {}
        live = bool((payload.get("data") or {}).get("live", False))
        summary = {"resumed": 0, "paused": 0, "dry_run": not live}

        conn = _conn()
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, owner_uid, scope, target_uid, mode, resume_at, "
                    "balance_threshold FROM dll_pause_rules WHERE active=TRUE"
                )
                rules = cur.fetchall()
                now = datetime.now()
                for rid, owner, scope, target, mode, resume_at, threshold in rules:
                    group_uid = target if scope == "group" else None
                    balance = _client_balance(cur, owner)

                    if mode == "until" and resume_at is not None and resume_at <= now:
                        for imei in _expand(cur, scope, target):
                            if not live:
                                summary["resumed"] += 1
                                continue
                            if _set_pause(cur, imei, "resume"):
                                summary["resumed"] += 1
                                _log_event(cur, owner, imei, group_uid, "resume",
                                           "auto_resume", balance, "worker")
                        if live:
                            cur.execute(
                                "UPDATE dll_pause_rules SET active=FALSE, updated_at=NOW() "
                                "WHERE id=%s", (rid,))

                    elif mode == "balance" and threshold is not None and balance <= threshold:
                        for imei in _expand(cur, scope, target):
                            if not live:
                                summary["paused"] += 1
                                continue
                            if _set_pause(cur, imei, "pause"):
                                summary["paused"] += 1
                                _log_event(cur, owner, imei, group_uid, "pause",
                                           "low_balance", balance, "worker")
        conn.close()
        return reply("success", 200, "Pause rules evaluated", summary)
    except Exception as error:
        return reply("error", 500, str(error), "")


# ── Analytics (product owner) ────────────────────────────────────────────────

@pause_bp.route("/pause/analytics/<owner_uid>", methods=["GET"])
def PauseAnalytics(owner_uid):
    """Aggregate pause behaviour for an owner (last 30 days by default)."""
    try:
        conn = _conn()
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT action, COUNT(*) FROM dll_pause_events "
                    "WHERE owner_uid=%s AND created_at >= NOW() - INTERVAL '30 days' "
                    "GROUP BY action", (str(owner_uid),))
                by_action = {a: int(c) for a, c in cur.fetchall()}

                cur.execute(
                    "SELECT reason, COUNT(*) FROM dll_pause_events "
                    "WHERE owner_uid=%s AND action='pause' "
                    "AND created_at >= NOW() - INTERVAL '30 days' "
                    "GROUP BY reason ORDER BY COUNT(*) DESC", (str(owner_uid),))
                by_reason = [{"reason": r, "count": int(c)} for r, c in cur.fetchall()]

                cur.execute(
                    "SELECT AVG(balance_at_event) FROM dll_pause_events "
                    "WHERE owner_uid=%s AND action='pause' "
                    "AND balance_at_event IS NOT NULL "
                    "AND created_at >= NOW() - INTERVAL '30 days'", (str(owner_uid),))
                avg_bal_row = cur.fetchone()
                avg_balance_at_pause = float(avg_bal_row[0]) if avg_bal_row and avg_bal_row[0] is not None else None

                # Currently paused units for this owner.
                cur.execute(
                    """
                    SELECT COUNT(DISTINCT s.device_imei_number)
                    FROM dll_device_subscriptions s
                    JOIN dll_user_token_accounts a
                      ON a.token_billing_uid = s.token_billing_uid
                    WHERE a.client_uid=%s AND s.subscription_status='paused'
                    """, (str(owner_uid),))
                cp = cur.fetchone()
                currently_paused = int(cp[0]) if cp and cp[0] is not None else 0

        conn.close()
        return reply("success", 200, "Pause analytics", {
            "window_days": 30,
            "pauses": by_action.get("pause", 0),
            "resumes": by_action.get("resume", 0),
            "by_reason": by_reason,
            "avg_balance_at_pause": avg_balance_at_pause,
            "currently_paused": currently_paused,
        })
    except Exception as error:
        return reply("error", 500, str(error), "")
