"""
config.py — Centralised configuration loaded from environment variables.

Usage:
    from config import DB_LINK, BASE_URL, JWT_SECRET, JWT_ACCESS_EXPIRY_MINUTES, JWT_REFRESH_EXPIRY_DAYS
"""

import os
from dotenv import load_dotenv

load_dotenv()  # reads .env file in project root

DB_LINK = os.environ.get(
    "DATABASE_URL",
    "postgresql://flareconnect:Announcer-Flagpole-Dreary-Census-Strength-Polyester-Ended-Sequester-Pork-Smokiness-Relish-Useable-Headband6-Quantum-Untrue-Crudeness-Breeching-Phrasing-Deeply-QuenchUnselfish-Silo-Exponent-Peroxide-Sizzle-Estranged-Ergonomic-Editor-Tubby-Overarch-Smugly0-Freeness-Harmonize-Exonerate-Sterile-Nectar-Unrevised-Undertone-Bluish-Stagnate@165.232.128.208:5432/narva_dbl",
)

BASE_URL = os.environ.get(
    "BASE_URL",
    "https://narvas.3dservices.co.ug/",
)

# JWT configuration
JWT_SECRET = os.environ.get(
    "JWT_SECRET",
    "CHANGE-ME-in-production-use-a-strong-random-secret-key",
)
JWT_ACCESS_EXPIRY_MINUTES = int(os.environ.get("JWT_ACCESS_EXPIRY_MINUTES", "30"))
JWT_REFRESH_EXPIRY_DAYS = int(os.environ.get("JWT_REFRESH_EXPIRY_DAYS", "7"))

# CORS — allowed origins for credential-bearing requests
CORS_ORIGINS = os.environ.get(
    "CORS_ORIGINS",
    "http://localhost:5173,http://localhost:3000,https://narvas.3dservices.co.ug,https://cms.3dservices.net",
).split(",")
