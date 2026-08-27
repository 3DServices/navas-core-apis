"""
auto_renew_worker.py — Auto-Renew background worker (Phase 2).

Sweeps clients who have auto-renew enabled and, for each device whose
subscription has lapsed (expired/depleted or its token is exhausted), attaches
the next available token from the client's EXISTING wallet balance — the same
renewal primitive as POST /subscriptions/device/renew. No purchasing happens.

Safety:
  * DRY-RUN by default. When `live=False` the worker only records what it WOULD
    do to dll_auto_renew_log; it never mutates subscriptions. Flip AUTO_RENEW_LIVE
    (or call run_auto_renew_sweep(live=True)) once the behaviour is validated.
  * Uses config.DB_LINK directly so it is safe to call from a background thread
    (no Flask app context required).

Returns a summary dict from run_auto_renew_sweep().
"""

from datetime import datetime

import psycopg2

from config import DB_LINK


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


def _enabled_clients(conn):
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT client_uid, target_hours FROM dll_auto_renew_settings "
                "WHERE enabled = TRUE AND paused = FALSE"
            )
            return cur.fetchall()


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

                # Live renewal — mirrors POST /subscriptions/device/renew.
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


def run_auto_renew_sweep(live=False):
    """Run one auto-renew pass. Returns a summary dict."""
    summary = {
        'clients': 0,
        'renewed': 0,
        'would_renew': 0,
        'skipped_no_tokens': 0,
        'low_balance': 0,
        'errors': 0,
        'dry_run': not live,
    }
    conn = None
    try:
        conn = psycopg2.connect(DB_LINK)
        clients = _enabled_clients(conn)
        for client_uid, target_hours in clients:
            summary['clients'] += 1
            try:
                for imei in _lapsed_devices(conn, client_uid):
                    _renew_one(conn, client_uid, imei, live, summary)

                if target_hours is not None:
                    total_left = _total_hours_left(conn, client_uid)
                    if total_left <= float(target_hours):
                        with conn:
                            with conn.cursor() as cur:
                                _log(cur, client_uid, None, None, 'low_balance',
                                     f'Remaining {total_left}h at/below target '
                                     f'{target_hours}h.', not live)
                        summary['low_balance'] += 1
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
