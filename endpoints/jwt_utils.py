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
from . import db_pool
from datetime import datetime, timedelta, timezone
from flask import current_app, g, has_app_context
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
    Returns the payload dict or None if invalid/expired/blacklisted.

    Checks the dll_token_blacklist table to reject tokens that were
    explicitly revoked (e.g. on logout) before their natural expiry.
    """
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None

    # Check if this token has been explicitly revoked
    jti = payload.get("jti")
    if jti and _is_token_blacklisted(jti):
        return None

    return payload


# Where this request's blacklist answers are kept. Keyed on the jti, never
# blanket: a request that decodes two different tokens must get two different
# answers, and an authorisation path is the wrong place to be clever.
_BLACKLIST_CACHE_KEY = '_navas_blacklist_checks'


def _blacklist_cache():
    """This request's jti -> bool map, or None outside a request."""
    if not has_app_context():
        return None
    try:
        cache = getattr(g, _BLACKLIST_CACHE_KEY, None)
        if cache is None:
            cache = {}
            setattr(g, _BLACKLIST_CACHE_KEY, cache)
        return cache
    except Exception:                                      # noqa: BLE001
        return None


def _is_token_blacklisted(jti):
    """Check if a JTI exists in the blacklist table.

    Cached for the rest of the request. Every route with a permission
    decorator decodes the token twice -- once in the access guard
    (access_guard.py:440) and again in the decorator (globals.py 434, 491,
    525, 559) -- and each decode was costing a round trip to a database
    282 ms away. Measured at 1,148-1,270 ms per request on the dashboard
    routes, for an answer that cannot change mid-request.

    The cache lives on flask.g, so it dies with the request: a token revoked
    now is still rejected on the very next one. _get_user_permissions beside
    this does the same thing for the same reason.
    """
    key = str(jti)
    cache = _blacklist_cache()
    if cache is not None and key in cache:
        return cache[key]

    answer = _blacklist_lookup(key)
    if cache is not None:
        cache[key] = answer
    return answer


def _blacklist_lookup(jti):
    """The uncached database check. Fails OPEN -- see the handler below."""
    try:
        dbconnect = db_pool.connect()
        try:
            with dbconnect:
                with dbconnect.cursor() as cursor:
                    cursor.execute(
                        "SELECT 1 FROM dll_token_blacklist WHERE jti = %s",
                        (str(jti),)
                    )
                    return cursor.rowcount > 0
        finally:
            dbconnect.close()
    except Exception:
        # If the blacklist table doesn't exist yet or DB is down,
        # fail open to avoid locking out all users during migration.
        # Log this so it gets noticed.
        print(f"[WARN] Token blacklist check failed for jti={jti}")
        return False


def blacklist_access_token(jti, account_uid, expires_at):
    """
    Add a JWT's JTI to the blacklist so it is rejected on future requests.
    Called during logout to immediately invalidate the access token.
    """
    # Drop any cached "not blacklisted" answer for this jti. The cache is
    # per-request and a logout ends the request, so this window is tiny --
    # but "the token I just revoked still passes" is not a sentence worth
    # leaving true for even one more call.
    cache = _blacklist_cache()
    if cache is not None:
        cache.pop(str(jti), None)

    try:
        dbconnect = db_pool.connect()
        try:
            with dbconnect:
                with dbconnect.cursor() as cursor:
                    cursor.execute("""
                        INSERT INTO dll_token_blacklist (jti, account_uid, expires_at)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (jti) DO NOTHING
                    """, (str(jti), str(account_uid), expires_at))
        finally:
            dbconnect.close()
    except Exception as e:
        print(f"[WARN] Failed to blacklist token jti={jti}: {e}")


def create_refresh_token(account_uid):
    """
    Create a refresh token, store its hash in the database,
    and return the raw token string (to be set as HttpOnly cookie).
    """
    raw_token = str(uuid.uuid4())
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    expires_at = datetime.now(timezone.utc) + timedelta(days=JWT_REFRESH_EXPIRY_DAYS)

    dbconnect = db_pool.connect()
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

    dbconnect = db_pool.connect()
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

    dbconnect = db_pool.connect()
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
    dbconnect = db_pool.connect()
    try:
        with dbconnect:
            with dbconnect.cursor() as cursor:
                cursor.execute("""
                    UPDATE dll_refresh_tokens SET revoked = TRUE
                    WHERE account_uid = %s AND revoked = FALSE
                """, (str(account_uid),))
    finally:
        dbconnect.close()
