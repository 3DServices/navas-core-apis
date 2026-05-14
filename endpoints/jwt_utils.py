"""
jwt_utils.py — JWT token creation, verification, and refresh-token management.

Access tokens:  Short-lived JWTs sent in Authorization header.
Refresh tokens: Long-lived opaque tokens stored in HttpOnly cookies
                and persisted in `dll_refresh_tokens` table.
"""

import jwt
import uuid
import hashlib
import psycopg2
from datetime import datetime, timedelta, timezone
from flask import current_app
from config import JWT_SECRET, JWT_ACCESS_EXPIRY_MINUTES, JWT_REFRESH_EXPIRY_DAYS


def create_access_token(account_uid, account_role, account_type, account_root):
    """Create a short-lived JWT access token."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": account_uid,
        "role": account_role,
        "type": account_type,
        "root": account_root,
        "iat": now,
        "exp": now + timedelta(minutes=JWT_ACCESS_EXPIRY_MINUTES),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def decode_access_token(token):
    """
    Decode and verify a JWT access token.
    Returns the payload dict or None if invalid/expired.
    """
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None


def create_refresh_token(account_uid):
    """
    Create a refresh token, store its hash in the database,
    and return the raw token string (to be set as HttpOnly cookie).
    """
    raw_token = str(uuid.uuid4())
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    expires_at = datetime.now(timezone.utc) + timedelta(days=JWT_REFRESH_EXPIRY_DAYS)

    dbconnect = psycopg2.connect(current_app.config['db_link'])
    try:
        with dbconnect:
            with dbconnect.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO dll_refresh_tokens (token_hash, account_uid, expires_at)
                    VALUES (%s, %s, %s)
                """, (token_hash, str(account_uid), expires_at))
    finally:
        dbconnect.close()

    return raw_token, expires_at


def validate_refresh_token(raw_token):
    """
    Validate a refresh token against the database.
    Returns account_uid if valid, None otherwise.
    """
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

    dbconnect = psycopg2.connect(current_app.config['db_link'])
    try:
        with dbconnect:
            with dbconnect.cursor() as cursor:
                cursor.execute("""
                    SELECT account_uid, expires_at, revoked
                    FROM dll_refresh_tokens
                    WHERE token_hash = %s
                """, (token_hash,))

                if cursor.rowcount == 0:
                    return None

                row = cursor.fetchone()
                account_uid = row[0]
                expires_at = row[1]
                revoked = row[2]

                if revoked:
                    return None
                if expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
                    return None

                return account_uid
    finally:
        dbconnect.close()


def revoke_refresh_token(raw_token):
    """Revoke a single refresh token (logout from one device)."""
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

    dbconnect = psycopg2.connect(current_app.config['db_link'])
    try:
        with dbconnect:
            with dbconnect.cursor() as cursor:
                cursor.execute("""
                    UPDATE dll_refresh_tokens SET revoked = TRUE
                    WHERE token_hash = %s
                """, (token_hash,))
    finally:
        dbconnect.close()


def revoke_all_refresh_tokens(account_uid):
    """Revoke all refresh tokens for a user (logout from all devices)."""
    dbconnect = psycopg2.connect(current_app.config['db_link'])
    try:
        with dbconnect:
            with dbconnect.cursor() as cursor:
                cursor.execute("""
                    UPDATE dll_refresh_tokens SET revoked = TRUE
                    WHERE account_uid = %s AND revoked = FALSE
                """, (str(account_uid),))
    finally:
        dbconnect.close()
