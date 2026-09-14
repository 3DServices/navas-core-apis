"""
auto_renew_worker.py — Auto-Renew + Auto Top-Up background worker.

Two engines, run in one sweep per enabled client:

  1. AUTO-RENEW (existing): for each lapsed device, attach the next available
     token from the client's EXISTING wallet — the same primitive as
     POST /subscriptions/device/renew. No purchasing.

  2. AUTO TOP-UP (Phase 1): when the wallet runs low (total hours <= target),
     optionally BUY more tokens via mobile money so renewals never starve. The
     collection request (finance.MoMoPayment_Charge) triggers the customer's
     PIN prompt on their phone — the PIN is NEVER seen or stored by us. Guarded
     by explicit consent, a per-day cap, and configuration checks.

Every client also receives a low-balance reminder notification (in-app now;
other channels via notifier adapters later).

Safety:
  * DRY-RUN by default (live=False): logs what it WOULD do to dll_auto_renew_log
    and never mutates subscriptions or initiates any charge.
  * Uses config.DB_LINK directly (safe from a background thread; no app context).

Returns a summary dict from run_auto_renew_sweep().
"""

from datetime import datetime

import psycopg2

from config import DB_LINK
from .notifier import notify


# ── Logging ───────────────────────────────────────────────────────────────────

def _log(cur, client_uid, device_imei, token_uid, outcome, message, dry_run):
    """Best-effort audit row; never raises."""
    try:
        cur.execute(
            """
            INSERT INTO dll_auto_renew_log
                (client_uid, device_imei, token_billing_uid, outcome, message, dry_run)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (str(client_uid), device_imei, token_uid, outcome, message, dry_run),
        )
    except Exception as e:  # pragma: no cover - logging must not break the sweep
        print(f"[auto-renew] log failed: {e}")


# ── Reads ─────────────────────────────────────────────────────────────────────

_SETTINGS_COLS = (
    "client_uid, target_hours, top_up_enabled, top_up_token_uid, "
    "top_up_quantity, momo_number, daily_topup_limit, channels, consent_at"
)


def _enabled_clients(conn):
    """Enabled, non-paused clients with their full auto-renew + top-up settings."""
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT {_SETTINGS_COLS} FROM dll_auto_renew_settings "
                "WHERE enabled = TRUE AND paused = FALSE"
            )
            rows = cur.fetchall()
    out = []
    for r in rows:
        out.append({
            "client_uid": r[0],
            "target_hours": r[1],
            "top_up_enabled": r[2],
            "top_up_token_uid": r[3],
            "top_up_quantity": r[4] or 1,
            "momo_number": r[5],
            "daily_topup_limit": r[6] if r[6] is not None else 1,
            "channels": r[7] or "in_app",
            "consent_at": r[8],
        })
    return out


def _lapsed_devices(conn, client_uid):
    """Distinct device IMEIs (for this client) whose subscription has run out."""
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT s.device_imei_number
                FROM dll_device_subscriptions s
                JOIN dll_user_token_accounts a
                  ON a.token_billing_uid = s.token_billing_uid
                WHERE a.client_uid = %s
                  AND (s.subscription_status IN ('expired', 'depleted')
                       OR COALESCE(a.token_hours_left::numeric, 0) <= 0)
                """,
                (str(client_uid),),
            )
            return [r[0] for r in cur.fetchall()]


def _total_hours_left(conn, client_uid):
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COALESCE(SUM(token_hours_left::numeric), 0) "
                "FROM dll_user_token_accounts "
                "WHERE client_uid = %s AND token_status = 'active'",
                (str(client_uid),),
            )
            row = cur.fetchone()
            return float(row[0]) if row and row[0] is not None else 0.0


def _next_available_token(cur, client_uid):
    """Oldest wallet token (FIFO) with hours left that isn't already tracking
    an active device. Returns token_billing_uid or None."""
    cur.execute(
        """
        SELECT a.token_billing_uid
        FROM dll_user_token_accounts a
        WHERE a.client_uid = %s
          AND a.token_status = 'active'
          AND COALESCE(a.token_hours_left::numeric, 0) > 0
          AND a.token_billing_uid NOT IN (
              SELECT token_billing_uid FROM dll_device_subscriptions
              WHERE subscription_status = 'active'
          )
        ORDER BY a.id ASC
        LIMIT 1
        """,
        (str(client_uid),),
    )
    row = cur.fetchone()
    return row[0] if row else None


def _topups_today(cur, client_uid):
    """How many auto top-ups were initiated (or would-be, in dry-run) today."""
    cur.execute(
        """
        SELECT COUNT(*) FROM dll_auto_renew_log
        WHERE client_uid = %s
          AND outcome IN ('top_up_initiated', 'would_top_up')
          AND created_at::date = CURRENT_DATE
        """,
        (str(client_uid),),
    )
    row = cur.fetchone()
    return int(row[0]) if row and row[0] is not None else 0


def _token_price(cur, token_uid):
    """(amount, currency, country) for a token package, or None if not priced."""
    cur.execute(
        "SELECT token_amount, token_currency, billing_unit "
        "FROM dll_tokens_registry WHERE token_id = %s",
        (str(token_uid),),
    )
    row = cur.fetchone()
    if not row or row[0] is None:
        return None
    currency = str(row[1]).upper()
    country = {"UGX": "uganda", "KES": "kenya"}.get(currency)
    return (row[0], currency, country, row[2])  # amount, currency, country, validity


# ── Renew (existing) ────────────────────────────────────────────────────────────

def _renew_one(conn, client_uid, imei, live, summary):
    try:
        with conn:
            with conn.cursor() as cur:
                token_uid = _next_available_token(cur, client_uid)
                if token_uid is None:
                    _log(cur, client_uid, imei, None, 'skipped_no_tokens',
                         'No available wallet token to renew from.', not live)
                    summary['skipped_no_tokens'] += 1
                    return

                if not live:
                    _log(cur, client_uid, imei, token_uid, 'would_renew',
                         'Dry run — would attach this token.', True)
                    summary['would_renew'] += 1
                    return

                now = datetime.now()
                cur.execute(
                    "UPDATE dll_user_token_accounts SET token_status = 'active' "
                    "WHERE token_billing_uid = %s",
                    (str(token_uid),),
                )
                cur.execute(
                    "UPDATE dll_device_subscriptions SET subscription_status = 'depleted' "
                    "WHERE device_imei_number = %s",
                    (str(imei),),
                )
                cur.execute(
                    "INSERT INTO dll_device_subscriptions "
                    "(subscription_status, start_date, start_counting_time, "
                    " device_imei_number, token_billing_uid) "
                    "VALUES ('active', %s, %s, %s, %s)",
                    (now.date().isoformat(), now.strftime('%H:%M:%S'),
                     str(imei), str(token_uid)),
                )
                _log(cur, client_uid, imei, token_uid, 'renewed',
                     'Auto-renewed from wallet.', False)
                summary['renewed'] += 1
    except Exception as e:
        summary['errors'] += 1
        try:
            with conn:
                with conn.cursor() as cur:
                    _log(cur, client_uid, imei, None, 'error', str(e), not live)
        except Exception:
            pass


# ── Auto top-up (Phase 1) ───────────────────────────────────────────────────────

def _maybe_top_up(conn, s, total_left, live, summary):
    """Initiate a mobile-money top-up for a low client, subject to consent + caps.

    The collection request prompts the customer for their PIN on their phone;
    we never see or store it. On success we log a pending payment row so the
    existing webhook provisions the tokens (same path as a manual buy).
    """
    client_uid = s["client_uid"]
    if not s.get("top_up_enabled"):
        return
    channels = s.get("channels", "in_app")

    try:
        with conn:
            with conn.cursor() as cur:
                # Guards ---------------------------------------------------------
                if s.get("consent_at") is None:
                    _log(cur, client_uid, None, None, 'topup_no_consent',
                         'Auto top-up enabled but no consent recorded.', not live)
                    return
                if not s.get("top_up_token_uid") or not s.get("momo_number"):
                    _log(cur, client_uid, None, None, 'topup_misconfigured',
                         'Missing top-up token package or mobile money number.', not live)
                    return

                cap = int(s.get("daily_topup_limit") or 1)
                if _topups_today(cur, client_uid) >= cap:
                    _log(cur, client_uid, None, None, 'topup_capped',
                         f'Daily top-up cap ({cap}) reached.', not live)
                    summary['topup_capped'] += 1
                    notify(cur, client_uid,
                           'Top-up limit reached',
                           'Your tokens are low but today\'s auto top-up limit was '
                           'reached. Tap to buy more tokens.',
                           'low_balance', channels)
                    return

                priced = _token_price(cur, s["top_up_token_uid"])
                if priced is None:
                    _log(cur, client_uid, None, None, 'topup_misconfigured',
                         'Top-up token package has no price.', not live)
                    return
                amount, currency, country, validity = priced
                qty = int(s.get("top_up_quantity") or 1)
                total = float(amount) * qty

                # Dry-run --------------------------------------------------------
                if not live:
                    _log(cur, client_uid, None, s["top_up_token_uid"], 'would_top_up',
                         f'Dry run — would charge {currency} {total:g} to '
                         f'{s["momo_number"]} for {qty} token(s).', True)
                    summary['would_top_up'] += 1
                    notify(cur, client_uid,
                           'Auto top-up (preview)',
                           f'Tokens are low ({total_left:g}h left). Auto top-up would '
                           f'buy {qty} token(s) for {currency} {total:g}.',
                           'top_up', channels)
                    return

                # Live charge ----------------------------------------------------
                if country is None:
                    _log(cur, client_uid, None, None, 'top_up_failed',
                         f'Unsupported currency {currency} for auto top-up.', False)
                    summary['top_up_failed'] += 1
                    return

                import uuid
                from .finance import MoMoPayment_Charge  # lazy: avoids import cycle

                ref = str(uuid.uuid4())
                resp = MoMoPayment_Charge(
                    s["momo_number"], country, currency, str(total), ref)

                if isinstance(resp, dict) and resp.get('status') == 'success':
                    remote = (resp.get('data') or {}).get('api_referance', '')
                    cur.execute(
                        "INSERT INTO dll_payment_logs "
                        "(payment_uid, payment_account, token_number, token_validity, "
                        " total_cost, payment_currency, payment_date, payment_status, "
                        " payment_owner, remote_uid, token_quantity) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s, 'pending', "
                        " 'auto_topup', %s, %s)",
                        (ref, str(client_uid), s["top_up_token_uid"], validity,
                         total, currency, datetime.now().date().isoformat(),
                         remote, qty),
                    )
                    cur.execute(
                        "UPDATE dll_auto_renew_settings SET last_topup_at = NOW() "
                        "WHERE client_uid = %s", (str(client_uid),))
                    _log(cur, client_uid, None, s["top_up_token_uid"], 'top_up_initiated',
                         f'Charged {currency} {total:g} to {s["momo_number"]} '
                         f'(ref {ref}).', False)
                    summary['top_up_initiated'] += 1
                    notify(cur, client_uid,
                           'Approve your top-up',
                           f'We sent a mobile money request for {currency} {total:g}. '
                           'Enter your PIN on your phone to keep tracking active.',
                           'top_up', channels)
                else:
                    _log(cur, client_uid, None, None, 'top_up_failed',
                         f'Gateway did not accept the charge: {resp}', False)
                    summary['top_up_failed'] += 1
                    notify(cur, client_uid,
                           'Top-up failed',
                           'We could not start your automatic top-up. Please buy '
                           'tokens manually to avoid tracking downtime.',
                           'top_up', channels)
    except Exception as e:
        summary['errors'] += 1
        try:
            with conn:
                with conn.cursor() as cur:
                    _log(cur, client_uid, None, None, 'error',
                         f'top-up: {e}', not live)
        except Exception:
            pass


# ── Sweep ───────────────────────────────────────────────────────────────────────

def run_auto_renew_sweep(live=False):
    """Run one auto-renew + auto-top-up pass. Returns a summary dict."""
    summary = {
        'clients': 0,
        'renewed': 0,
        'would_renew': 0,
        'skipped_no_tokens': 0,
        'low_balance': 0,
        'would_top_up': 0,
        'top_up_initiated': 0,
        'top_up_failed': 0,
        'topup_capped': 0,
        'errors': 0,
        'dry_run': not live,
    }
    conn = None
    try:
        conn = psycopg2.connect(DB_LINK)
        clients = _enabled_clients(conn)
        for s in clients:
            client_uid = s["client_uid"]
            target_hours = s["target_hours"]
            summary['clients'] += 1
            try:
                # 1. Keep lapsed devices alive from existing wallet tokens.
                for imei in _lapsed_devices(conn, client_uid):
                    _renew_one(conn, client_uid, imei, live, summary)

                # 2. Low-balance detection → reminder + (optional) auto top-up.
                if target_hours is not None:
                    total_left = _total_hours_left(conn, client_uid)
                    if total_left <= float(target_hours):
                        with conn:
                            with conn.cursor() as cur:
                                _log(cur, client_uid, None, None, 'low_balance',
                                     f'Remaining {total_left}h at/below target '
                                     f'{target_hours}h.', not live)
                                notify(cur, client_uid,
                                       'Tokens running low',
                                       f'You have about {total_left:g}h of tracking '
                                       'left. Top up to avoid downtime.',
                                       'low_balance', s.get("channels", "in_app"))
                        summary['low_balance'] += 1
                        _maybe_top_up(conn, s, total_left, live, summary)
            except Exception as e:
                summary['errors'] += 1
                print(f"[auto-renew] client {client_uid} failed: {e}")
    except Exception as e:
        summary['errors'] += 1
        print(f"[auto-renew] sweep failed: {e}")
    finally:
        if conn:
            conn.close()
    print(f"[auto-renew] sweep summary: {summary}")
    return summary
