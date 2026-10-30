from flask import Blueprint

from app.routes.admin import admin_bp
from app.routes.auth import auth_bp
from app.routes.events import events_bp
from app.routes.registrations import registrations_bp

api = Blueprint("api", __name__)
api.register_blueprint(auth_bp)
api.register_blueprint(events_bp)
api.register_blueprint(registrations_bp)
api.register_blueprint(admin_bp)
