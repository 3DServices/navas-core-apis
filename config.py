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