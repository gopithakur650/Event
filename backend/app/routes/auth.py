import re
import os
from datetime import datetime, timedelta, timezone

from flask import Blueprint, current_app, g, jsonify, request
from flask_jwt_extended import (
    create_access_token,
    get_jwt,
    get_jwt_identity,
    jwt_required,
    set_access_cookies,
    unset_jwt_cookies,
)
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.models import Event, RevokedToken, User
from app.routes.common import require_roles
from app.services import log_activity, send_email, upload_file
from extensions import db, limiter

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")
RESET_SALT = "gatherly-password-reset-v1"


def serializer():
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"])


def normalized_email(value):
    return value.strip().lower() if isinstance(value, str) else ""


def optional_text(data, key):
    value = data.get(key, "")
    return value.strip() if isinstance(value, str) else ""


@auth_bp.post("/register")
@limiter.limit("5 per hour")
def register():
    data = request.get_json(silent=True) or {}
    name = data.get("full_name", "").strip() if isinstance(data.get("full_name"), str) else ""
    email = normalized_email(data.get("email"))
    password = data.get("password")
    role = data.get("role", "user")
    phone = optional_text(data, "phone")
    organization_name = optional_text(data, "organization_name")
    if not name or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        return jsonify({"error": "A name and valid email are required"}), 400
    if not phone or (role == "organizer" and not organization_name):
        return jsonify({"error": "Phone number and organizer organization name are required"}), 400
    if not isinstance(password, str) or len(password) < 8:
        return jsonify({"error": "Password must be at least 8 characters"}), 400
    if role not in ("user", "organizer"):
        return jsonify({"error": "Only user and organizer registration is public"}), 400
    if db.session.query(User.id).filter(func.lower(User.email) == email).first():
        return jsonify({"error": "An account with this email already exists"}), 409

    user = User(
        full_name=name,
        email=email,
        phone=phone,
        role=role,
        organization_name=organization_name or None,
        organization_description=optional_text(data, "organization_description") or None,
        organization_address=optional_text(data, "organization_address") or None,
        approval_status="pending" if role == "organizer" else "approved",
    )
    user.set_password(password)
    db.session.add(user)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "An account with this email already exists"}), 409
    log_activity(user, "account_registered", f"{role.title()} account registered")
    db.session.commit()
    if role == "organizer":
        send_email(user.email, "Gatherly organizer application received",
                   "Your organizer application has been received and is awaiting admin review.")
    else:
        send_email(user.email, "Welcome to Gatherly",
                   f"Hi {user.full_name}, your Gatherly account has been created.")
    return jsonify({"user": user.to_dict()}), 201


@auth_bp.post("/login")
@limiter.limit("10 per minute")
def login():
    data = request.get_json(silent=True) or {}
    email = normalized_email(data.get("email"))
    password = data.get("password")
    user = User.query.filter(func.lower(User.email) == email).first()
    if not user or not isinstance(password, str) or not user.check_password(password):
        return jsonify({"error": "Invalid email or password"}), 401
    if user.account_status != "active":
        return jsonify({"error": "Account is unavailable"}), 403
    remember_me = data.get("remember_me") is True
    expires = timedelta(days=30) if remember_me else None
    token = create_access_token(
        identity=str(user.id),
        expires_delta=expires,
        additional_claims={"auth_version": user.auth_version},
    )
    response = jsonify({"user": user.to_dict()})
    set_access_cookies(
        response,
        token,
        max_age=timedelta(days=30) if remember_me else None,
    )
    return response


@auth_bp.get("/me")
@jwt_required()
def me():
    user = db.session.get(User, int(get_jwt_identity()))
    if not user or user.account_status != "active":
        return jsonify({"error": "Account is unavailable"}), 403
    return jsonify({"user": user.to_dict()})


@auth_bp.post("/logout")
@jwt_required()
def logout():
    token = get_jwt()
    db.session.add(RevokedToken(
        jti=token["jti"],
        expires_at=datetime.fromtimestamp(token["exp"], timezone.utc).replace(tzinfo=None),
    ))
    db.session.commit()
    response = jsonify({"message": "Signed out"})
    unset_jwt_cookies(response)
    return response


@auth_bp.patch("/me")
@require_roles("user", "organizer", "admin")
def update_profile():
    data = request.get_json(silent=True) or {}
    allowed = {
        "full_name", "phone", "college_name", "department", "student_id",
        "organization_name", "organization_description", "organization_address",
    }
    for field in allowed.intersection(data):
        value = data[field]
        if not isinstance(value, str) or len(value.strip()) > 500:
            return jsonify({"error": f"{field.replace('_', ' ').title()} must be text no longer than 500 characters"}), 400
        value = value.strip()
        if field in ("full_name", "phone") and not value:
            return jsonify({"error": f"{field.replace('_', ' ').title()} cannot be empty"}), 400
        setattr(g.current_user, field, value or None)
    if not allowed.intersection(data):
        return jsonify({"error": "No editable profile fields were provided"}), 400
    db.session.commit()
    return jsonify({"user": g.current_user.to_dict()})


@auth_bp.put("/me/password")
@require_roles("user", "organizer", "admin")
def change_password():
    data = request.get_json(silent=True) or {}
    current_password = data.get("current_password")
    new_password = data.get("new_password")
    if not isinstance(current_password, str) or not g.current_user.check_password(current_password):
        return jsonify({"error": "Current password is incorrect"}), 400
    if not isinstance(new_password, str) or len(new_password) < 10:
        return jsonify({"error": "New password must be at least 10 characters"}), 400
    g.current_user.set_password(new_password)
    g.current_user.auth_version += 1
    db.session.commit()
    response = jsonify({"message": "Password changed. Sign in again."})
    unset_jwt_cookies(response)
    return response


@auth_bp.post("/forgot-password")
@limiter.limit("5 per hour")
def forgot_password():
    data = request.get_json(silent=True) or {}
    email = normalized_email(data.get("email"))
    user = User.query.filter(func.lower(User.email) == email).first()
    if user and user.account_status == "active":
        token = serializer().dumps({"user_id": user.id}, salt=RESET_SALT)
        frontend = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173").split(",")[0].strip()
        link = f"{frontend}/reset-password?token={token}"
        send_email(user.email, "Reset your Gatherly password",
                   f"Use this link within 30 minutes to reset your password:\n\n{link}")
    return jsonify({"message": "If that account exists, password reset instructions have been sent."})


@auth_bp.post("/reset-password")
@limiter.limit("10 per hour")
def reset_password():
    data = request.get_json(silent=True) or {}
    token = data.get("token")
    password = data.get("password")
    if not isinstance(token, str) or not isinstance(password, str) or len(password) < 10:
        return jsonify({"error": "A valid reset token and password of at least 10 characters are required"}), 400
    try:
        claims = serializer().loads(token, salt=RESET_SALT, max_age=1800)
    except SignatureExpired:
        return jsonify({"error": "Password reset link has expired"}), 400
    except BadSignature:
        return jsonify({"error": "Password reset link is invalid"}), 400
    user = db.session.get(User, claims.get("user_id"))
    if not user or user.account_status != "active":
        return jsonify({"error": "Password reset link is invalid"}), 400
    user.set_password(password)
    user.auth_version += 1
    db.session.commit()
    return jsonify({"message": "Password reset. You can now sign in."})


@auth_bp.post("/me/profile-image")
@require_roles("user", "organizer", "admin")
def profile_image():
    try:
        stored = upload_file(request.files.get("file"), "image")
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    g.current_user.profile_image = stored
    db.session.commit()
    return jsonify({"user": g.current_user.to_dict()})


@auth_bp.post("/me/organization-files")
@require_roles("organizer")
def organization_files():
    user = g.current_user
    updated = []
    try:
        if request.files.get("logo"):
            user.organization_logo = upload_file(request.files["logo"], "image")
            updated.append("organization_logo")
        if request.files.get("document"):
            user.supporting_document = upload_file(request.files["document"], "document")
            updated.append("supporting_document")
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    if not updated:
        return jsonify({"error": "Choose a logo or supporting document"}), 400
    db.session.commit()
    return jsonify({"user": user.to_dict(), "uploaded": updated})


@auth_bp.delete("/me")
@require_roles("user", "organizer", "admin")
def delete_account():
    user = g.current_user
    if user.role == "admin":
        return jsonify({"error": "Admin accounts cannot be self-deleted"}), 403
    if Event.query.filter_by(organizer_id=user.id).first():
        return jsonify({"error": "Organizers with event history cannot be deleted; ask an admin to deactivate the account"}), 409
    user_id = user.id
    db.session.delete(user)
    db.session.commit()
    return jsonify({"message": "Account deleted", "user_id": user_id})
