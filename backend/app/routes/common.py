from functools import wraps

from flask import g, jsonify
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request

from app.models import User
from extensions import db


def require_roles(*roles):
    def decorator(handler):
        @wraps(handler)
        def wrapped(*args, **kwargs):
            verify_jwt_in_request()
            user = db_user_from_token()
            if not user or user.account_status != "active":
                return jsonify({"error": "Account is unavailable"}), 403
            if user.role not in roles:
                return jsonify({"error": "Insufficient permissions"}), 403
            g.current_user = user
            return handler(*args, **kwargs)

        return wrapped

    return decorator


def db_user_from_token():
    try:
        return db.session.get(User, int(get_jwt_identity()))
    except (TypeError, ValueError):
        return None
