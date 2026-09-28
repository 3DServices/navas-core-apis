"""
config.py — Centralised configuration loaded from environment variables.

IMPORTANT: All secrets (DATABASE_URL, JWT_SECRET) MUST be set via environment
variables or a .env file.  The application will refuse to start if they are
missing — there are no hardcoded fallback values for security-sensitive keys.

Usage:
    from config import DB_LINK, BASE_URL, JWT_SECRET, JWT_ACCESS_EXPIRY_MINUTES, JWT_REFRESH_EXPIRY_DAYS
"""

import os
import sys
from dotenv import load_dotenv

load_dotenv()  # reads .env file in project root


# ── Helper: require an env var or abort at startup ──────────────────────────

def _require_env(name: str) -> str:
    """Return the value of an environment variable or terminate with an error."""
    value = os.environ.get(name)
    if not value:
        print(
            f"[FATAL] Required environment variable '{name}' is not set.\n"
            f"        Set it in your .env file or system environment before starting the app.",
            file=sys.stderr,
        )
        sys.exit(1)
    return value


# ── Required secrets (no defaults — must be in env / .env) ─────────────────

DB_LINK = _require_env("DATABASE_URL")

JWT_SECRET = _require_env("JWT_SECRET")


# ── Optional settings (safe defaults) ──────────────────────────────────────

BASE_URL = os.environ.get(
    "BASE_URL",
    "https://narvas.3dservices.co.ug/",
)

JWT_ACCESS_EXPIRY_MINUTES = int(os.environ.get("JWT_ACCESS_EXPIRY_MINUTES", "30"))
JWT_REFRESH_EXPIRY_DAYS = int(os.environ.get("JWT_REFRESH_EXPIRY_DAYS", "7"))

# ── Waswa AI Assistant (OpenRouter) ────────────────────────────────────────
# The API key is optional at startup so the app still boots without it; the
# /assistant/chat endpoint returns a clear 503 when it is not configured.
# Set OPENROUTER_API_KEY in your .env (gitignored) or server environment.
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "openai/gpt-4o")
OPENROUTER_SITE_URL = os.environ.get("OPENROUTER_SITE_URL", BASE_URL)
OPENROUTER_SITE_NAME = os.environ.get("OPENROUTER_SITE_NAME", "OLIWA Mobile")

# ── Reverse geocoding (place names) ─────────────────────────────────────────
# Optional. When GOOGLE_MAPS_API_KEY is set the /data-stream/location/geocoding
# endpoint uses Google's reverse geocoder (reliable at fleet volume); otherwise
# it falls back to the free Nominatim (OpenStreetMap) service, which is rate-
# limited and only suitable for light use. Keep the key in .env (gitignored) or
# the server environment — never commit it.
GOOGLE_MAPS_API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY", "")


# ── Auto-Renew worker (Phase 2) ────────────────────────────────────────────
# AUTO_RENEW_ENABLED starts the embedded scheduler. AUTO_RENEW_LIVE controls
# whether the sweep actually mutates subscriptions; when false it only records
# what it WOULD do to dll_auto_renew_log (safe dry-run). Keep both off until
# the behaviour has been validated against real data.
AUTO_RENEW_ENABLED = os.environ.get("AUTO_RENEW_ENABLED", "false").lower() == "true"
AUTO_RENEW_LIVE = os.environ.get("AUTO_RENEW_LIVE", "false").lower() == "true"
AUTO_RENEW_INTERVAL_MINUTES = int(
    os.environ.get("AUTO_RENEW_INTERVAL_MINUTES", "15"))

# CORS — allowed origins for credential-bearing requests

CORS_ORIGINS = [
    origin.strip()
    for origin in os.environ.get(
        "CORS_ORIGINS",
        "http://localhost:5173,http://localhost:5174,http://localhost:5175,http://localhost:3000,https://narvas.3dservices.co.ug,https://cms.3dservices.net",
    ).split(",")
]


# CORS_ORIGINS = os.environ.get(
#     "CORS_ORIGINS",
#     "http://localhost:5173,http://localhost:5174,http://localhost:5175,http://localhost:3000,https://narvas.3dservices.co.ug,https://cms.3dservices.net",
# ).split(",")

# ── Cassandra (device telemetry) ───────────────────────────────────────────
# The password used to sit in plain text in six endpoint files — data.py,
# data_handler.py, devices.py, device_configs.py, management.py and
# statistics.py — each with its own copy. It is read from the environment
# here instead, and the app refuses to start without it: a default would put
# the password straight back into the repository.
#
# The contact points and username are not secrets, so they keep working
# defaults; override them per environment when the cluster moves.
CASSANDRA_KEYSPACE = os.environ.get("CASSANDRA_KEYSPACE", "navas_iot_dbx")
CASSANDRA_CONTACT_POINTS = [
    host.strip()
    for host in os.environ.get("CASSANDRA_CONTACT_POINTS", "165.232.128.208").split(",")
    if host.strip()
]
CASSANDRA_PORT = int(os.environ.get("CASSANDRA_PORT", "9042"))
CASSANDRA_USERNAME = os.environ.get("CASSANDRA_USERNAME", "cassandra")
CASSANDRA_PASSWORD = _require_env("CASSANDRA_PASSWORD")
CASSANDRA_LOCAL_DC = os.environ.get("CASSANDRA_LOCAL_DC", "datacenter1")


# ── Payments (Santripe mobile money) ───────────────────────────────────────
# Optional at startup so the app still boots without it; MoMoPayment_Charge
# refuses the charge with a clear error when it is missing, rather than
# sending a request that the gateway rejects.
SANTRIPE_API_KEY = os.environ.get("SANTRIPE_API_KEY", "")
SANTRIPE_COLLECTIONS_URL = os.environ.get(
    "SANTRIPE_COLLECTIONS_URL",
    "https://optimus.santripe.com/collections/mobile-money",
)


# ── Distance lookups (distancematrix.ai) ───────────────────────────────────
# Optional. Without it Calculate_DistanceX reports that distances are not
# configured instead of calling the service with an empty key.
DISTANCEMATRIX_API_KEY = os.environ.get("DISTANCEMATRIX_API_KEY", "")
