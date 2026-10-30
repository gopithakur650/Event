import csv
from io import BytesIO, StringIO

import os

from flask import Blueprint, current_app, g, jsonify, make_response, request, send_from_directory
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from decimal import InvalidOperation

from app.models import (
    ActivityLog,
    Attendance,
    Category,
    Event,
    Feedback,
    Notification,
    Payment,
    Registration,
    Ticket,
    User,
    utc_iso,
    utcnow,
)
from app.routes.common import require_roles
from app.routes.events import event_fields
from app.services import log_activity, notify_event_participants, notify_user, send_email
from extensions import db

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


@admin_bp.get("/dashboard")
@require_roles("admin")
def dashboard():
    monthly_events = db.session.query(
        month_expression(Event.created_at).label("month"),
        func.count(Event.id),
    ).group_by("month").order_by("month").all()
    monthly_registrations = db.session.query(
        month_expression(Registration.created_at).label("month"),
        func.count(Registration.id),
    ).group_by("month").order_by("month").all()
    categories = db.session.query(Category.name, func.count(Event.id)).outerjoin(
        Event, Event.category_id == Category.id
    ).group_by(Category.id, Category.name).order_by(Category.name).all()
    revenue = db.session.query(func.coalesce(func.sum(Payment.amount), 0)).filter(
        Payment.payment_status == "paid"
    ).scalar()
    return jsonify({
        "total_users": User.query.filter_by(role="user").count(),
        "total_organizers": User.query.filter_by(role="organizer").count(),
        "total_events": Event.query.count(),
        "approved_events": Event.query.filter_by(approval_status="approved").count(),
        "pending_events": Event.query.filter_by(approval_status="pending").count(),
        "rejected_events": Event.query.filter_by(approval_status="rejected").count(),
        "total_registrations": Registration.query.filter_by(status="confirmed").count(),
        "total_revenue": float(revenue or 0),
        "monthly_events": [{"month": month, "count": count} for month, count in monthly_events],
        "monthly_registrations": [{"month": month, "count": count} for month, count in monthly_registrations],
        "category_distribution": [{"category": name, "count": count} for name, count in categories],
        "recent_activity": [{
            "id": item.id,
            "actor_role": item.actor_role,
            "action": item.action,
            "description": item.description,
            "created_at": utc_iso(item.created_at),
        } for item in ActivityLog.query.order_by(ActivityLog.created_at.desc()).limit(10).all()],
        "upcoming_events": [
            item.to_dict() for item in Event.query.filter_by(
                approval_status="approved", event_status="active"
            ).filter(Event.start_at >= db.session.query(func.now()).scalar()).order_by(Event.start_at.asc()).limit(5).all()
        ],
    })


def month_expression(column):
    if db.engine.dialect.name == "mysql":
        return func.date_format(column, "%Y-%m")
    return func.strftime("%Y-%m", column)


@admin_bp.get("/events")
@require_roles("admin")
def list_events():
    query = Event.query
    status = request.args.get("approval_status")
    if status in ("draft", "pending", "approved", "rejected"):
        query = query.filter(Event.approval_status == status)
    search = request.args.get("search", "").strip()
    if search:
        query = query.filter(or_(Event.title.ilike(f"%{search}%"), Event.city.ilike(f"%{search}%")))
    page = max(1, request.args.get("page", 1, type=int))
    per_page = min(100, max(1, request.args.get("per_page", 25, type=int)))
    result = query.order_by(Event.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
    return jsonify({
        "items": [event.to_dict(include_private=True) for event in result.items],
        "page": result.page,
        "pages": result.pages,
        "total": result.total,
    })


@admin_bp.get("/events/pending")
@require_roles("admin")
def pending_events():
    events = Event.query.filter_by(approval_status="pending").order_by(Event.created_at.asc()).all()
    return jsonify({"items": [event.to_dict(include_private=True) for event in events]})


@admin_bp.put("/events/<int:event_id>/approve")
@require_roles("admin")
def approve_event(event_id):
    event = db.session.get(Event, event_id)
    if not event or event.approval_status != "pending":
        return jsonify({"error": "Pending event not found"}), 404
    event.approval_status = "approved"
    event.rejection_reason = None
    notify_user(event.organizer_id, "Event approved", f"{event.title} is approved and now visible to participants.", "event_approved")
    log_activity(g.current_user, "event_approved", f"Approved event: {event.title}")
    db.session.commit()
    send_email(event.organizer.email, f"Your event was approved: {event.title}",
               "Your event is now published on Gatherly.")
    return jsonify({"event": event.to_dict()})


@admin_bp.put("/events/<int:event_id>/reject")
@require_roles("admin")
def reject_event(event_id):
    event = db.session.get(Event, event_id)
    data = request.get_json(silent=True) or {}
    reason = data.get("reason", "").strip() if isinstance(data.get("reason"), str) else ""
    if not event or event.approval_status != "pending":
        return jsonify({"error": "Pending event not found"}), 404
    if not reason:
        return jsonify({"error": "A rejection reason is required"}), 400
    event.approval_status = "rejected"
    event.rejection_reason = reason[:500]
    notify_user(event.organizer_id, "Event needs changes", f"{event.title}: {reason[:500]}", "event_rejected")
    log_activity(g.current_user, "event_rejected", f"Rejected event: {event.title}")
    db.session.commit()
    send_email(event.organizer.email, f"Update to your event: {event.title}", reason[:500])
    return jsonify({"event": event.to_dict(include_private=True)})


@admin_bp.put("/events/<int:event_id>")
@require_roles("admin")
def edit_event(event_id):
    event = db.session.get(Event, event_id)
    if not event:
        return jsonify({"error": "Event not found"}), 404
    try:
        values = event_fields(request.get_json(silent=True) or {}, event)
    except (AttributeError, KeyError, TypeError, ValueError, InvalidOperation):
        return jsonify({"error": "Event details are invalid"}), 400
    for field, value in values.items():
        setattr(event, field, value)
    notify_event_participants(event, f"Update to {event.title}", "An administrator updated your event details.")
    log_activity(g.current_user, "event_edited", f"Edited event: {event.title}")
    db.session.commit()
    return jsonify({"event": event.to_dict(include_private=True)})


@admin_bp.get("/users")
@require_roles("admin")
def users():
    role = request.args.get("role")
    query = User.query
    if role in ("user", "organizer", "admin"):
        query = query.filter_by(role=role)
    status = request.args.get("status")
    if status in ("active", "inactive"):
        query = query.filter_by(account_status=status)
    search = request.args.get("search", "").strip()
    if search:
        query = query.filter(or_(User.full_name.ilike(f"%{search}%"), User.email.ilike(f"%{search}%")))
    page = max(1, request.args.get("page", 1, type=int))
    per_page = min(100, max(1, request.args.get("per_page", 25, type=int)))
    result = query.order_by(User.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
    return jsonify({"items": [item.to_dict() for item in result.items], "page": result.page, "pages": result.pages, "total": result.total})


@admin_bp.put("/users/<int:user_id>")
@require_roles("admin")
def edit_user(user_id):
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404
    data = request.get_json(silent=True) or {}
    for field in ("full_name", "phone", "college_name", "department", "student_id"):
        if field in data:
            value = data[field]
            if not isinstance(value, str) or len(value.strip()) > 180:
                return jsonify({"error": f"{field.replace('_', ' ').title()} must be text no longer than 180 characters"}), 400
            setattr(user, field, value.strip() or None)
    db.session.commit()
    return jsonify({"user": user.to_dict()})


@admin_bp.put("/users/<int:user_id>/status")
@require_roles("admin")
def set_user_status(user_id):
    user = db.session.get(User, user_id)
    status = (request.get_json(silent=True) or {}).get("account_status")
    if not user or user.role == "admin":
        return jsonify({"error": "User not found"}), 404
    if status not in ("active", "inactive"):
        return jsonify({"error": "account_status must be active or inactive"}), 400
    if user.account_status != status:
        user.auth_version += 1
    user.account_status = status
    log_activity(g.current_user, f"user_{status}", f"Set account {user.email} to {status}")
    db.session.commit()
    return jsonify({"user": user.to_dict()})


@admin_bp.delete("/users/<int:user_id>")
@require_roles("admin")
def delete_user(user_id):
    user = db.session.get(User, user_id)
    if (
        not user
        or user.role == "admin"
        or Event.query.filter_by(organizer_id=user_id).first()
        or Registration.query.filter_by(user_id=user_id).first()
    ):
        return jsonify({"error": "User cannot be deleted; deactivate the account instead"}), 409
    log_activity(g.current_user, "user_deleted", f"Deleted account {user.email}")
    db.session.delete(user)
    db.session.commit()
    return "", 204


@admin_bp.get("/organizers")
@require_roles("admin")
def organizers():
    status = request.args.get("approval_status")
    query = User.query.filter_by(role="organizer")
    if status in ("pending", "approved", "rejected"):
        query = query.filter_by(approval_status=status)
    search = request.args.get("search", "").strip()
    if search:
        query = query.filter(or_(User.full_name.ilike(f"%{search}%"), User.organization_name.ilike(f"%{search}%"), User.email.ilike(f"%{search}%")))
    return jsonify({"items": [item.to_dict() for item in query.order_by(User.created_at.desc()).limit(200).all()]})


@admin_bp.get("/organizers/<int:user_id>/files/<kind>")
@require_roles("admin")
def organizer_file(user_id, kind):
    user = db.session.get(User, user_id)
    if not user or user.role != "organizer" or kind not in ("logo", "document"):
        return jsonify({"error": "Organizer file not found"}), 404
    filename = user.organization_logo if kind == "logo" else user.supporting_document
    if not filename:
        return jsonify({"error": "Organizer file not found"}), 404
    upload_root = os.path.abspath(os.path.join(
        current_app.root_path, "..", current_app.config["UPLOAD_FOLDER"]
    ))
    return send_from_directory(upload_root, filename, as_attachment=kind == "document")


@admin_bp.put("/organizers/<int:user_id>/approve")
@require_roles("admin")
def approve_organizer(user_id):
    user = db.session.get(User, user_id)
    if not user or user.role != "organizer":
        return jsonify({"error": "Organizer not found"}), 404
    user.approval_status = "approved"
    user.rejection_reason = None
    user.account_status = "active"
    notify_user(user.id, "Organizer application approved", "You can now create events on Gatherly.", "organizer_approved")
    log_activity(g.current_user, "organizer_approved", f"Approved organizer: {user.email}")
    db.session.commit()
    send_email(user.email, "Your Gatherly organizer application was approved", "You can now sign in and create events.")
    return jsonify({"user": user.to_dict()})


@admin_bp.put("/organizers/<int:user_id>/reject")
@require_roles("admin")
def reject_organizer(user_id):
    user = db.session.get(User, user_id)
    data = request.get_json(silent=True) or {}
    reason = data.get("reason", "").strip() if isinstance(data.get("reason"), str) else ""
    if not user or user.role != "organizer":
        return jsonify({"error": "Organizer not found"}), 404
    if not reason:
        return jsonify({"error": "A rejection reason is required"}), 400
    user.approval_status = "rejected"
    user.rejection_reason = reason[:500]
    notify_user(user.id, "Organizer application update", reason[:500], "organizer_rejected")
    log_activity(g.current_user, "organizer_rejected", f"Rejected organizer: {user.email}")
    db.session.commit()
    send_email(user.email, "Your Gatherly organizer application needs attention", reason[:500])
    return jsonify({"user": user.to_dict()})


@admin_bp.put("/organizers/<int:user_id>/status")
@require_roles("admin")
def organizer_status(user_id):
    user = db.session.get(User, user_id)
    active = (request.get_json(silent=True) or {}).get("active")
    if not user or user.role != "organizer" or not isinstance(active, bool):
        return jsonify({"error": "Organizer and boolean active value are required"}), 400
    user.account_status = "active" if active else "inactive"
    user.auth_version += 1
    log_activity(g.current_user, "organizer_status_changed", f"Set organizer {user.email} active={active}")
    db.session.commit()
    return jsonify({"user": user.to_dict()})


@admin_bp.get("/registrations")
@require_roles("admin")
def registrations():
    query = Registration.query.join(User).join(Event)
    search = request.args.get("search", "").strip()
    if search:
        query = query.filter(or_(User.full_name.ilike(f"%{search}%"), User.email.ilike(f"%{search}%"), Event.title.ilike(f"%{search}%")))
    status = request.args.get("status")
    if status in ("confirmed", "cancelled", "pending_payment", "expired"):
        query = query.filter(Registration.status == status)
    payment_status = request.args.get("payment_status")
    if payment_status in ("not_required", "pending", "paid", "failed", "refunded", "expired"):
        query = query.filter(Registration.payment_status == payment_status)
    items = query.order_by(Registration.created_at.desc()).limit(500).all()
    return jsonify({"items": [{
        "id": item.id,
        "participant": item.user.full_name,
        "email": item.user.email,
        "event": item.event.title,
        "event_id": item.event_id,
        "registration_number": item.registration_number,
        "registration_status": item.status,
        "payment_status": item.payment_status,
        "attendance_status": "checked_in" if item.ticket and item.ticket.attendance else "not_checked_in",
        "created_at": utc_iso(item.created_at),
    } for item in items]})


@admin_bp.put("/registrations/<int:registration_id>/cancel")
@require_roles("admin")
def cancel_registration(registration_id):
    from app.models import Ticket

    registration = db.session.get(Registration, registration_id)
    if not registration:
        return jsonify({"error": "Registration not found"}), 404
    registration.status = "cancelled"
    ticket = Ticket.query.filter_by(registration_id=registration.id).first()
    if ticket:
        ticket.status = "cancelled"
    refund_note = " A refund has not been processed and will be handled separately." if registration.payment_status == "paid" else ""
    notify_user(registration.user_id, "Registration cancelled", f"Your registration for {registration.event.title} was cancelled by an administrator.{refund_note}", "registration_cancelled")
    log_activity(g.current_user, "registration_cancelled", f"Cancelled registration {registration.registration_number}")
    db.session.commit()
    return jsonify({"message": "Registration cancelled"})


@admin_bp.get("/categories")
@require_roles("admin")
def categories():
    return jsonify({"items": [category.to_dict() | {"active": category.active} for category in Category.query.order_by(Category.name).all()]})


@admin_bp.post("/categories")
@require_roles("admin")
def create_category():
    data = request.get_json(silent=True) or {}
    name = data.get("name", "").strip() if isinstance(data.get("name"), str) else ""
    if not name or len(name) > 80:
        return jsonify({"error": "Category name must contain 1 to 80 characters"}), 400
    description = data.get("description", "")
    if not isinstance(description, str):
        return jsonify({"error": "Category description must be text"}), 400
    category = Category(name=name, description=description.strip()[:255])
    db.session.add(category)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "A category with this name already exists"}), 409
    return jsonify({"category": category.to_dict() | {"active": category.active}}), 201


@admin_bp.put("/categories/<int:category_id>")
@require_roles("admin")
def update_category(category_id):
    category = db.session.get(Category, category_id)
    data = request.get_json(silent=True) or {}
    if not category:
        return jsonify({"error": "Category not found"}), 404
    if "name" in data:
        if not isinstance(data["name"], str) or not data["name"].strip() or len(data["name"].strip()) > 80:
            return jsonify({"error": "Category name must contain 1 to 80 characters"}), 400
        category.name = data["name"].strip()
    if "description" in data:
        if not isinstance(data["description"], str):
            return jsonify({"error": "Description must be text"}), 400
        category.description = data["description"].strip()[:255]
    if "active" in data:
        if not isinstance(data["active"], bool):
            return jsonify({"error": "active must be a boolean"}), 400
        category.active = data["active"]
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "A category with this name already exists"}), 409
    return jsonify({"category": category.to_dict() | {"active": category.active}})


@admin_bp.delete("/categories/<int:category_id>")
@require_roles("admin")
def deactivate_category(category_id):
    category = db.session.get(Category, category_id)
    if not category:
        return jsonify({"error": "Category not found"}), 404
    category.active = False
    db.session.commit()
    return "", 204


@admin_bp.get("/reports")
@require_roles("admin")
def reports_csv():
    report_type = request.args.get("type", "events")
    output = StringIO()
    writer = csv.writer(output)
    if report_type == "events":
        writer.writerow(["Event", "Category", "Organizer", "Start", "Approval", "Status", "Capacity", "Confirmed registrations"])
        for event in Event.query.order_by(Event.start_at).all():
            writer.writerow([event.title, event.category.name, event.organizer.organization_name or event.organizer.full_name, utc_iso(event.start_at), event.approval_status, event.event_status, event.capacity, Registration.query.filter_by(event_id=event.id, status="confirmed").count()])
    elif report_type == "registrations":
        writer.writerow(["Participant", "Email", "Event", "Registration", "Payment", "Attendance", "Created"])
        for item in Registration.query.join(User).join(Event).order_by(Registration.created_at).all():
            writer.writerow([item.user.full_name, item.user.email, item.event.title, item.status, item.payment_status, "checked_in" if item.ticket and item.ticket.attendance else "not_checked_in", utc_iso(item.created_at)])
    elif report_type == "revenue":
        writer.writerow(["Event", "Participant", "Amount", "Currency", "Payment status", "Transaction", "Paid at"])
        for payment in Payment.query.join(Registration).join(Event).join(User).order_by(Payment.created_at).all():
            writer.writerow([payment.registration.event.title, payment.registration.user.full_name, payment.amount, payment.currency, payment.payment_status, payment.transaction_id or "", utc_iso(payment.payment_date) if payment.payment_date else ""])
    elif report_type == "attendance":
        writer.writerow(["Event", "Participant", "Registration", "Check-in time"])
        for item in Attendance.query.join(Ticket).join(Registration).order_by(Attendance.check_in_time).all():
            writer.writerow([item.ticket.registration.event.title, item.ticket.registration.user.full_name, item.ticket.registration.registration_number, utc_iso(item.check_in_time)])
    elif report_type == "categories":
        writer.writerow(["Category", "Events"])
        for name, count in db.session.query(Category.name, func.count(Event.id)).outerjoin(Event).group_by(Category.id, Category.name).all():
            writer.writerow([name, count])
    else:
        return jsonify({"error": "Report type must be events, registrations, revenue, attendance, or categories"}), 400
    response = make_response(output.getvalue())
    response.headers["Content-Type"] = "text/csv; charset=utf-8"
    response.headers["Content-Disposition"] = f'attachment; filename="gatherly-{report_type}-report.csv"'
    return response


@admin_bp.get("/reports.pdf")
@require_roles("admin")
def reports_pdf():
    output = BytesIO()
    document = canvas.Canvas(output, pagesize=letter)
    document.setTitle("Gatherly analytics report")
    document.setFont("Helvetica-Bold", 20)
    document.drawString(48, 750, "Gatherly analytics report")
    document.setFont("Helvetica", 11)
    lines = [
        f"Generated: {utc_iso(utcnow())}",
        f"Users: {User.query.filter_by(role='user').count()}",
        f"Organizers: {User.query.filter_by(role='organizer').count()}",
        f"Events: {Event.query.count()}",
        f"Approved events: {Event.query.filter_by(approval_status='approved').count()}",
        f"Confirmed registrations: {Registration.query.filter_by(status='confirmed').count()}",
        f"Checked-in tickets: {Attendance.query.count()}",
        f"Collected payments (INR): {db.session.query(func.coalesce(func.sum(Payment.amount), 0)).filter(Payment.payment_status == 'paid').scalar()}",
    ]
    y = 705
    for line in lines:
        document.drawString(55, y, line)
        y -= 25
    document.setFont("Helvetica-Bold", 13)
    document.drawString(55, y - 10, "Event category distribution")
    y -= 38
    document.setFont("Helvetica", 10)
    for name, count in db.session.query(Category.name, func.count(Event.id)).outerjoin(Event).group_by(Category.id, Category.name).all():
        document.drawString(65, y, f"{name}: {count}")
        y -= 18
    document.save()
    output.seek(0)
    response = make_response(output.getvalue())
    response.headers["Content-Type"] = "application/pdf"
    response.headers["Content-Disposition"] = 'attachment; filename="gatherly-analytics-report.pdf"'
    return response


@admin_bp.get("/activity")
@require_roles("admin")
def activity():
    entries = ActivityLog.query.order_by(ActivityLog.created_at.desc()).limit(200).all()
    return jsonify({"items": [{
        "id": item.id,
        "actor_id": item.actor_id,
        "actor_role": item.actor_role,
        "action": item.action,
        "description": item.description,
        "created_at": utc_iso(item.created_at),
    } for item in entries]})


@admin_bp.get("/feedback")
@require_roles("admin")
def feedback_report():
    entries = Feedback.query.order_by(Feedback.created_at.desc()).limit(500).all()
    return jsonify({"items": [{
        "event": db.session.get(Event, item.event_id).title,
        "participant": db.session.get(User, item.user_id).full_name,
        "rating": item.rating,
        "comments": item.comments,
        "suggestions": item.suggestions,
        "created_at": utc_iso(item.created_at),
    } for item in entries]})
