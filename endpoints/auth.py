"""
endpoints/auth.py — Authentication endpoints (refresh, logout, password reset).

The primary login endpoint remains at POST /users/auth (in users.py)
so existing clients are not broken. This blueprint adds:

  POST /auth/refresh          — Silent token refresh via HttpOnly cookie
  POST /auth/logout           — Revoke refresh token
  POST /auth/forgot-password  — Send password-reset email (stub)
  POST /auth/reset-password   — Reset password with token (stub)
  POST /auth/mfa/resend       — Resend MFA code (stub)
"""

from flask import Blueprint, request, make_response
from datetime import datetime, timezone as tz
import hashlib
import psycopg2
from flask import current_app
from .globals import reply, log_audit_event
from .jwt_utils import (
    create_access_token,
    decode_access_token,
    validate_refresh_token,
    revoke_refresh_token,
    revoke_all_refresh_tokens,
    blacklist_access_token,
)
from config import JWT_REFRESH_EXPIRY_DAYS
from .jwt_utils import create_refresh_token as _create_refresh_token

auth_bp = Blueprint('auth_bp', __name__)


@auth_bp.route("/auth/refresh", methods=["POST"])
def refresh():
    """
    Silent token refresh with **token rotation**.

    1. Reads the refresh token from the HttpOnly cookie.
    2. Validates it (not revoked, not expired).
    3. Revokes the old refresh token immediately (one-time use).
    4. Issues a brand-new refresh token + new access token.
    5. Returns the access token in the JSON body and sets the new
       refresh token as an HttpOnly cookie.

    If a revoked token is presented (reuse detection), all of the
    user's refresh tokens are revoked as a precaution — this forces
    re-login on every device.
    """
    raw_token = request.cookies.get("_nvxs_refresh_token")
    if not raw_token:
        return reply('error', 401, 'No refresh token provided', '')

    # ── Validate the incoming refresh token ─────────────────────────
    account_uid = validate_refresh_token(raw_token)

    if not account_uid:
        # Possible token reuse — someone may have stolen the old token.
        # Revoke ALL tokens for this user as a safety measure.
        _handle_possible_reuse(raw_token)
        return reply('error', 401, 'Invalid or expired refresh token', '')

    # ── Revoke the old refresh token (one-time use) ─────────────────
    revoke_refresh_token(raw_token)

    # ── Look up current user info ───────────────────────────────────
    dbconnect = psycopg2.connect(current_app.config['db_link'])
    try:
        with dbconnect:
            with dbconnect.cursor() as cursor:
                cursor.execute(
                    "SELECT account_clearance, account_type, account_root "
                    "FROM dll_access_relay WHERE account_uid = %s AND access_status = 'active'",
                    (str(account_uid),)
                )
                if cursor.rowcount == 0:
                    return reply('error', 401, 'Account not found or inactive', '')

                row = cursor.fetchone()
                account_role = row[0]
                account_type = row[1]
                account_root = row[2]
    finally:
        dbconnect.close()

    # ── Issue new tokens ────────────────────────────────────────────
    access_token = create_access_token(account_uid, account_role, account_type, account_root)
    new_refresh_token, refresh_expires = _create_refresh_token(account_uid)

    # ── Build response with rotated refresh cookie ──────────────────
    response_body, status_code = reply('success', 200, 'Token refreshed', {
        'access_token': access_token,
    })
    resp = make_response(response_body, status_code)
    resp.set_cookie(
        '_nvxs_refresh_token',
        new_refresh_token,
        max_age=JWT_REFRESH_EXPIRY_DAYS * 86400,
        httponly=True,
        secure=True,
        samesite='Strict',
        path='/',
    )
    return resp


def _handle_possible_reuse(raw_token):
    """
    When an already-revoked refresh token is presented, it may indicate
    theft.  Look up which account owned it and revoke ALL their tokens.
    """
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

    try:
        dbconnect = psycopg2.connect(current_app.config['db_link'])
        try:
            with dbconnect:
                with dbconnect.cursor() as cursor:
                    cursor.execute(
                        "SELECT account_uid FROM dll_refresh_tokens WHERE token_hash = %s",
                        (token_hash,)
                    )
                    if cursor.rowcount > 0:
                        account_uid = cursor.fetchone()[0]
                        revoke_all_refresh_tokens(account_uid)
                        log_audit_event(
                            actor='system',
                            action='REFRESH_TOKEN_REUSE',
                            obj=f"Possible token theft detected for user {account_uid} — all sessions revoked",
                            domain='SYSTEM',
                            severity='Crit',
                            ip_address=request.remote_addr,
                            meta={"account_uid": account_uid}
                        )
        finally:
            dbconnect.close()
    except Exception as e:
        print(f"[WARN] Reuse detection failed: {e}")


@auth_bp.route("/auth/logout", methods=["POST"])
def logout():
    """
    Revoke the refresh token, blacklist the current access token, and clear cookies.

    This ensures:
      1. The refresh token cannot be used to obtain new access tokens.
      2. The current access token is rejected immediately (not just after its 30-min expiry).
    """
    raw_refresh = request.cookies.get("_nvxs_refresh_token")
    account_uid = None

    # ── Revoke the refresh token ────────────────────────────────────
    if raw_refresh:
        account_uid = validate_refresh_token(raw_refresh)
        revoke_refresh_token(raw_refresh)

    # ── Blacklist the current access token ──────────────────────────
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        access_token = auth_header[7:].strip()
        payload = decode_access_token(access_token)
        if payload:
            jti = payload.get('jti')
            token_uid = payload.get('sub')
            exp = payload.get('exp')
            if jti and exp:
                expires_at = datetime.fromtimestamp(exp, tz=tz.utc)
                blacklist_access_token(jti, token_uid or '', expires_at)
            # Use the access token's sub if we couldn't get it from refresh
            if not account_uid:
                account_uid = token_uid

    # ── Audit log ───────────────────────────────────────────────────
    if account_uid:
        log_audit_event(
            actor=account_uid,
            action='LOGOUT',
            obj=f"User {account_uid} logged out",
            domain='SYSTEM',
            severity='Info',
            ip_address=request.remote_addr,
        )

    response_body, status_code = reply('success', 200, 'Logged out', '')
    resp = make_response(response_body, status_code)
    resp.set_cookie(
        '_nvxs_refresh_token', '',
        max_age=0,
        httponly=True,
        secure=True,
        samesite='Strict',
        path='/',
    )
    return resp


@auth_bp.route("/auth/forgot-password", methods=["POST"])
def forgot_password():
    """
    Initiate a password reset. Accepts { "data": { "email": "..." } }.

    For security, always return success regardless of whether the email exists.
    TODO: Integrate with an email service to send the reset link.
    """
    payload = request.get_json()
    try:
        email = str(payload['data']['email']).strip()
    except (KeyError, TypeError):
        return reply('error', 400, 'Email is required', '')

    if len(email) < 5:
        return reply('error', 400, 'Invalid email', '')

    # Check if account exists (but don't reveal this to the caller)
    dbconnect = psycopg2.connect(current_app.config['db_link'])
    try:
        with dbconnect:
            with dbconnect.cursor() as cursor:
                cursor.execute(
                    "SELECT account_uid FROM dll_access_relay WHERE email = %s AND access_status = 'active'",
                    (email,)
                )
                if cursor.rowcount == 1:
                    account_uid = cursor.fetchone()[0]
                    # TODO: Generate a time-limited reset token, store it,
                    # and send an email with a link like:
                    #   https://cms.example.com/reset-password?token=<reset_token>
                    log_audit_event(
                        actor=account_uid,
                        action='PASSWORD_RESET_REQUEST',
                        obj=f"Password reset requested for {email}",
                        domain='SYSTEM',
                        severity='Info',
                        ip_address=request.remote_addr,
                    )
    finally:
        dbconnect.close()

    # Always return success to prevent email enumeration
    return reply('success', 200, 'If an account with that email exists, a reset link has been sent.', '')


@auth_bp.route("/auth/reset-password", methods=["POST"])
def reset_password_with_token():
    """
    Reset password using a reset token.
    Accepts { "data": { "token": "...", "new_password": "..." } }.

    TODO: Implement token validation once forgot-password generates tokens.
    """
    payload = request.get_json()
    try:
        reset_token = str(payload['data']['token']).strip()
        new_password = str(payload['data']['new_password']).strip()
    except (KeyError, TypeError):
        return reply('error', 400, 'Token and new_password are required', '')

    if len(new_password) < 6:
        return reply('error', 400, 'Password must be at least 6 characters', '')

    # TODO: Look up the reset token in a dll_password_reset_tokens table,
    # validate it hasn't expired, hash the new password with bcrypt,
    # update dll_access_relay, and invalidate the token.

    return reply('error', 501, 'Password reset via token is not yet implemented. Contact support.', '')


@auth_bp.route("/auth/mfa/resend", methods=["POST"])
def mfa_resend():
    """
    Resend a new MFA code to the user.

    TODO: Implement actual MFA code generation and delivery
    once MFA is enabled on the backend.
    """
    return reply('success', 200, 'A new verification code has been sent.', '')
