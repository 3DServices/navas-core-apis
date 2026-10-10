"""
waswa_data_auth.py -- the access token the Waswa agent presents to the data API.

WHY A TOKEN OF ITS OWN
The agent no longer opens database connections; it asks /waswa/data/* for what
it needs. Those routes must not trust anything the agent says about whose data
it wants, so every call carries a short-lived token, minted by POST
/assistant/chat only after the user's own sign-in token has been verified. The
token names that user in `sub`, and the data API reads the account from there
and nowhere else -- not from the URL, not from the body.

It is deliberately NOT a user access token:
  * signed with a different key, so it cannot be replayed against the rest of
    the API (decode_access_token uses JWT_SECRET and rejects it), and a user
    token cannot be replayed against the data API;
  * carries aud/iss, which are required on the way in, and PyJWT refuses a
    token with an `aud` wherever no audience is expected;
  * lives minutes, not the half hour a user token does, and only for one turn.

Key: WASWA_DATA_TOKEN_SECRET when set. Otherwise a key derived from JWT_SECRET
with HMAC, so a fresh checkout works without new configuration while the two
keys still differ. Set the variable in production so the two can be rotated
independently.
"""

import hashlib
import hmac
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone

import jwt

from config import JWT_SECRET

ISSUER = 'navas-waswa-agent'
AUDIENCE = 'waswa-data-api'
SCOPE = 'waswa:data'
_ALGORITHM = 'HS256'

# Long enough for a turn at its worst -- six tool rounds plus a forced answer
# and a v2 repair, each model call allowed 45s -- and no longer.
_DEFAULT_TTL_SECONDS = 600


def _ttl_seconds():
    try:
        return max(30, int(os.environ.get('WASWA_DATA_TOKEN_TTL_SECONDS',
                                          _DEFAULT_TTL_SECONDS)))
    except ValueError:
        return _DEFAULT_TTL_SECONDS


def _signing_key():
    configured = (os.environ.get('WASWA_DATA_TOKEN_SECRET') or '').strip()
    if configured and configured != JWT_SECRET:
        return configured
    if configured:
        # The same key as user tokens would let a data token pass as a user
        # token. Refuse the configuration rather than the request.
        logging.error('WASWA_DATA_TOKEN_SECRET equals JWT_SECRET; ignoring it '
                      'and using a derived key instead')
    return hmac.new(JWT_SECRET.encode('utf-8'), b'waswa-data-api/v1',
                    hashlib.sha256).hexdigest()


def mint(account_uid):
    """A data-API token acting for [account_uid], already authenticated."""
    if not account_uid:
        raise ValueError('a data token needs an account')
    now = datetime.now(timezone.utc)
    payload = {
        'iss': ISSUER,
        'aud': AUDIENCE,
        'sub': str(account_uid),
        'scope': SCOPE,
        'iat': now,
        'nbf': now,
        'exp': now + timedelta(seconds=_ttl_seconds()),
        'jti': str(uuid.uuid4()),
    }
    return jwt.encode(payload, _signing_key(), algorithm=_ALGORITHM)


def verify(token):
    """The account a valid token acts for, or None.

    Every claim that matters is required, so a token missing one is refused
    rather than accepted with a default.
    """
    if not token:
        return None
    try:
        payload = jwt.decode(
            token, _signing_key(), algorithms=[_ALGORITHM],
            audience=AUDIENCE, issuer=ISSUER,
            options={'require': ['exp', 'iat', 'nbf', 'sub', 'aud', 'iss',
                                 'jti', 'scope']})
    except jwt.InvalidTokenError:
        return None
    if payload.get('scope') != SCOPE:
        return None
    return payload.get('sub') or None
