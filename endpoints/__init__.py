from flask import Flask
from .users import users_bp
from .devices import devices_bp
from .clients import clients_bp
from .device_configs import device_config
from .data import data_stream
from .management import management_bp
from .geozones import geozones_bp
from .groups import groups_bp
from .data_handler import data_handler_bp
from .finance import finance_bp
from .json_reports_data import _jsonReports_data_bp
from .tokens_billing import _token_billing
from .veba import _veba
from .statistics import _statistics
from .metrics import metrics_bp as api_metrics_bp, register_metrics_middleware
from .gateways import gateways_bp
from .system32 import _system32
from .server_metrics import metrics_bp as server_metrics_bp
from .system_hardware_apis import _system_hardware_apis
from .rbac import rbac_bp
from .audit import audit_bp
from .auth import auth_bp

def Sentinel_Fleet():
    app = Flask(__name__)

    app.register_blueprint(users_bp)
    app.register_blueprint(devices_bp)
    app.register_blueprint(clients_bp)
    app.register_blueprint(device_config)
    app.register_blueprint(data_stream)
    app.register_blueprint(management_bp)
    app.register_blueprint(geozones_bp)
    app.register_blueprint(groups_bp)
    app.register_blueprint(data_handler_bp)
    app.register_blueprint(finance_bp)
    app.register_blueprint(_jsonReports_data_bp)
    app.register_blueprint(_token_billing)
    app.register_blueprint(_veba)
    app.register_blueprint(_statistics)
    app.register_blueprint(api_metrics_bp)
    app.register_blueprint(gateways_bp)
    app.register_blueprint(_system32)
    app.register_blueprint(server_metrics_bp)
    app.register_blueprint(_system_hardware_apis)
    app.register_blueprint(rbac_bp)
    app.register_blueprint(audit_bp)
    app.register_blueprint(auth_bp)

    # Register metrics middleware
    register_metrics_middleware(app)

    return app
