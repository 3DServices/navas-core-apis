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
import psycopg2
from flask import current_app
from .globals import reply, log_audit_event
from .jwt_utils import (
    create_access_token,
    validate_refresh_token,
    revoke_refresh_token,
    revoke_all_refresh_tokens,
)
from config import JWT_REFRESH_EXPIRY_DAYS

auth_bp = Blueprint('auth_bp', __name__)


@auth_bp.route("/auth/refresh", methods=["POST"])
def refresh():
    """
    Silent token refresh.
    Reads the refresh token from the HttpOnly cookie,
    validates it, and returns a new access token.
    """
    raw_token = request.cookies.get("_nvxs_refresh_token")
    if not raw_token:
        return reply('error', 401, 'No refresh token provided', '')

    account_uid = validate_refresh_token(raw_token)
    if not account_uid:
        return reply('error', 401, 'Invalid or expired refresh token', '')

    # Look up current user info for the new access token
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

    access_token = create_access_token(account_uid, account_role, account_type, account_root)

    return reply('success', 200, 'Token refreshed', {
        'access_token': access_token,
    })


@auth_bp.route("/auth/logout", methods=["POST"])
def logout():
    """
    Revoke the refresh token and clear the cookie.
    """
    raw_token = request.cookies.get("_nvxs_refresh_token")

    if raw_token:
        # Try to get account_uid for audit logging before revoking
        account_uid = validate_refresh_token(raw_token)
        revoke_refresh_token(raw_token)

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
