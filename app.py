from flask import Flask
from endpoints import Sentinel_Fleet
from flask_cors import CORS, cross_origin
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from config import DB_LINK, BASE_URL, CORS_ORIGINS

app = Sentinel_Fleet()


CORS(
    app,
    resources={r"/*": {"origins": CORS_ORIGINS}},
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=[
        "Content-Type",
        "Authorization",
        "Auth-Key",
        "X-Requested-With",
        "Accept",
        "Origin",
    ],
    expose_headers=["Content-Type", "Content-Length"],
    supports_credentials=True,
    max_age=86400,
)

# Rate limiting — protects auth endpoints from brute-force
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=[],                       # no global limit
    storage_uri="memory://",
)

# Apply rate limits to auth endpoints
limiter.limit("5/minute")(app.view_functions.get('users_bp.auth_user', lambda: None))
limiter.limit("5/minute")(app.view_functions.get('auth_bp.refresh', lambda: None))
limiter.limit("3/minute")(app.view_functions.get('auth_bp.forgot_password', lambda: None))

# Optional: force OPTIONS to always succeed (extra safety)
@app.route("/", defaults={"path": ""}, methods=["OPTIONS"])
@app.route("/<path:path>", methods=["OPTIONS"])
@cross_origin(
    origins=CORS_ORIGINS,
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=[
        "Content-Type",
        "Authorization",
        "Auth-Key",
        "X-Requested-With",
        "Accept",
        "Origin",
    ],
    max_age=86400,
    supports_credentials=True,
)
def _preflight(path):
    return ("", 204)

app.config['db_link'] = DB_LINK
app.config['base_url'] = BASE_URL




if __name__ == '__main__':
    app.run(host="0.0.0.0", debug=True)