import os

from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv
from werkzeug.exceptions import RequestEntityTooLarge

load_dotenv()

from config import Config
from extensions import db, jwt, limiter, mail, migrate


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)
    if not app.config["DEBUG"] and not app.testing and (
        app.config["SECRET_KEY"] == "local-development-key-change-me"
        or app.config["JWT_SECRET_KEY"] == "local-jwt-key-change-me"
    ):
        raise RuntimeError("Set unique SECRET_KEY and JWT_SECRET_KEY values before production startup")

    origins = os.getenv(
        "FRONTEND_ORIGIN",
        "http://localhost:5173,http://127.0.0.1:5173",
    ).split(",")
    CORS(app, origins=[origin.strip() for origin in origins], supports_credentials=True)
    db.init_app(app)
    jwt.init_app(app)
    migrate.init_app(app, db)
    mail.init_app(app)
    limiter.init_app(app)
    os.makedirs(os.path.join(app.root_path, "..", app.config["UPLOAD_FOLDER"]), exist_ok=True)

    from app import models
    from app.routes import api

    app.register_blueprint(api, url_prefix="/api")

    @jwt.token_in_blocklist_loader
    def token_is_revoked(_header, payload):
        if db.session.get(models.RevokedToken, payload["jti"]) is not None:
            return True
        try:
            user = db.session.get(models.User, int(payload["sub"]))
        except (TypeError, ValueError):
            return True
        return (
            not user
            or user.account_status != "active"
            or payload.get("auth_version") != user.auth_version
        )

    @app.get("/api/health")
    def health():
        return jsonify({"status": "ok"})

    @app.get("/api/uploads/<path:filename>")
    def uploaded_file(filename):
        if not filename.startswith("images/") and not filename.startswith("images\\"):
            return jsonify({"error": "File not found"}), 404
        upload_root = os.path.abspath(os.path.join(
            app.root_path, "..", app.config["UPLOAD_FOLDER"]
        ))
        return send_from_directory(upload_root, filename)

    @app.errorhandler(RequestEntityTooLarge)
    def file_too_large(_error):
        return jsonify({"error": "The uploaded file exceeds the 5 MB limit"}), 413

    return app
