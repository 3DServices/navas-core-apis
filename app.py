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


# ── Auto-Renew scheduler (Phase 2, opt-in) ─────────────────────────────────
# Off by default. Enable with AUTO_RENEW_ENABLED=true; it stays in dry-run
# (logging only) until AUTO_RENEW_LIVE=true. For multi-worker deployments
# (e.g. gunicorn with several workers) prefer an external cron calling
# POST /subscriptions/auto-renew/run instead, so the sweep runs once per tick.
def _start_auto_renew_scheduler():
    import os
    from config import (
        AUTO_RENEW_ENABLED, AUTO_RENEW_LIVE, AUTO_RENEW_INTERVAL_MINUTES,
    )
    if not AUTO_RENEW_ENABLED:
        return
    # Under the Werkzeug debug reloader, only start in the child process.
    if os.environ.get('WERKZEUG_RUN_MAIN') == 'false':
        return
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from endpoints.auto_renew_worker import run_auto_renew_sweep
        scheduler = BackgroundScheduler(daemon=True)
        scheduler.add_job(
            lambda: run_auto_renew_sweep(live=AUTO_RENEW_LIVE),
            'interval',
            minutes=AUTO_RENEW_INTERVAL_MINUTES,
            id='auto_renew_sweep',
            replace_existing=True,
        )
        scheduler.start()
        mode = 'LIVE' if AUTO_RENEW_LIVE else 'dry-run'
        print(f"[auto-renew] scheduler started ({mode}, "
              f"every {AUTO_RENEW_INTERVAL_MINUTES}m)")
    except Exception as e:
        print(f"[auto-renew] scheduler failed to start: {e}")


_start_auto_renew_scheduler()


if __name__ == '__main__':
    app.run(host="0.0.0.0", debug=True)