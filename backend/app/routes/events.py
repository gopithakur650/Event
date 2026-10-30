import csv
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from io import StringIO

from flask import Blueprint, current_app, g, jsonify, make_response, request
from sqlalchemy import func, or_

from app.models import (
    Announcement,
    Attendance,
    Category,
    Event,
    Notification,
    Payment,
    Registration,
    Ticket,
    User,
    utc_iso,
    utcnow,
)
from app.routes.common import require_roles
from app.services import log_activity, notify_event_participants, send_email, upload_file
from extensions import db, limiter

events_bp = Blueprint("events", __name__, url_prefix="/events")
EDITABLE_TEXT_FIELDS = (
    "title", "description", "venue", "address", "city", "state", "postal_code",
    "online_meeting_link", "eligibility", "age_restriction",
    "department_restriction", "event_rules", "required_materials",
    "contact_person", "contact_email", "contact_phone", "website",
)


def parse_date(value):
    if not isinstance(value, str):
        raise ValueError
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def event_fields(data, event=None):
    values = {}
    for field in EDITABLE_TEXT_FIELDS:
        if field in data:
            value = data[field]
            if not isinstance(value, str):
                raise ValueError
            value = value.strip()
            if field in ("title", "description") and not value:
                raise ValueError
            values[field] = value or None
    if "category_id" in data or event is None:
        category_id = int(data.get("category_id", 0))
        category = db.session.get(Category, category_id)
        if not category or not category.active:
            raise ValueError
        values["category_id"] = category.id
    for field in ("start_at", "end_at", "registration_start", "registration_deadline"):
        if field in data or event is None:
            default = utc_iso(utcnow())
            values[field] = parse_date(data.get(field, default))
    if "capacity" in data or event is None:
        values["capacity"] = int(data.get("capacity", 0))
        if values["capacity"] < 1:
            raise ValueError
        if event and values["capacity"] < Registration.query.filter_by(
            event_id=event.id, status="confirmed"
        ).count():
            raise ValueError
    if "fee" in data or event is None:
        values["fee"] = Decimal(str(data.get("fee", 0)))
        if not values["fee"].is_finite() or values["fee"] < 0:
            raise ValueError
    if "event_type" in data or event is None:
        values["event_type"] = data.get("event_type", "offline")
        if values["event_type"] not in ("online", "offline", "hybrid"):
            raise ValueError
    start = values.get("start_at", event.start_at if event else None)
    end = values.get("end_at", event.end_at if event else None)
    registration_start = values.get(
        "registration_start", event.registration_start if event else None
    )
    deadline = values.get(
        "registration_deadline", event.registration_deadline if event else None
    )
    if start >= end or registration_start > deadline or deadline > start:
        raise ValueError
    return values


def public_events_query():
    return Event.query.join(Category).join(User, User.id == Event.organizer_id).filter(
        Event.approval_status == "approved",
        Event.event_status == "active",
        User.account_status == "active",
    )


@events_bp.get("")
def list_events():
    query = public_events_query()
    search = request.args.get("search", "").strip()
    category = request.args.get("category", "").strip()
    date_from = request.args.get("date_from")
    date_to = request.args.get("date_to")
    event_type = request.args.get("event_type")
    price = request.args.get("price")
    if search:
        query = query.filter(or_(
            Event.title.ilike(f"%{search}%"),
            Event.description.ilike(f"%{search}%"),
            Event.city.ilike(f"%{search}%"),
        ))
    if category:
        query = query.filter(or_(Category.name == category, Category.id == category if category.isdigit() else False))
    try:
        if date_from:
            query = query.filter(Event.start_at >= parse_date(date_from))
        if date_to:
            parsed_end = parse_date(date_to)
            if len(date_to) == 10:
                parsed_end += timedelta(days=1)
            query = query.filter(Event.start_at < parsed_end)
        if date_from and date_to and parse_date(date_from) >= parse_date(date_to):
            return jsonify({"error": "The end date must be on or after the start date"}), 400
    except (TypeError, ValueError):
        return jsonify({"error": "Date filters must be ISO dates"}), 400
    if event_type in ("online", "offline", "hybrid"):
        query = query.filter(Event.event_type == event_type)
    if price == "free":
        query = query.filter(Event.fee == 0)
    elif price == "paid":
        query = query.filter(Event.fee > 0)

    sort = request.args.get("sort", "upcoming")
    if sort == "newest":
        query = query.order_by(Event.created_at.desc())
    elif sort == "popular":
        registration_counts = db.session.query(
            Registration.event_id,
            func.count(Registration.id).label("total"),
        ).filter(Registration.status == "confirmed").group_by(Registration.event_id).subquery()
        query = query.outerjoin(registration_counts, Event.id == registration_counts.c.event_id)
        query = query.order_by(registration_counts.c.total.desc(), Event.start_at.asc())
    elif sort == "upcoming":
        query = query.filter(Event.start_at >= utcnow()).order_by(Event.start_at.asc())
    else:
        return jsonify({"error": "Sort must be upcoming, newest, or popular"}), 400

    page = max(1, request.args.get("page", 1, type=int))
    per_page = min(50, max(1, request.args.get("per_page", 12, type=int)))
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    return jsonify({
        "items": [event.to_dict() for event in pagination.items],
        "page": pagination.page,
        "pages": pagination.pages,
        "per_page": pagination.per_page,
        "total": pagination.total,
    })


@events_bp.get("/featured")
def featured_events():
    events = public_events_query().filter(Event.start_at >= utcnow()).order_by(
        Event.start_at.asc()
    ).limit(6).all()
    return jsonify({"items": [event.to_dict() for event in events]})


@events_bp.get("/upcoming")
def upcoming_events():
    events = public_events_query().filter(Event.start_at >= utcnow()).order_by(
        Event.start_at.asc()
    ).limit(12).all()
    return jsonify({"items": [event.to_dict() for event in events]})


@events_bp.get("/categories")
def list_categories():
    categories = Category.query.filter_by(active=True).order_by(Category.name).all()
    return jsonify({"items": [category.to_dict() for category in categories]})


@events_bp.get("/stats")
def public_stats():
    return jsonify({
        "events": public_events_query().count(),
        "participants": User.query.filter_by(role="user", account_status="active").count(),
        "organizers": User.query.filter_by(role="organizer", approval_status="approved", account_status="active").count(),
        "registrations": Registration.query.filter_by(status="confirmed").count(),
    })


@events_bp.post("/contact")
@limiter.limit("5 per hour")
def contact():
    data = request.get_json(silent=True) or {}
    name = data.get("name", "").strip() if isinstance(data.get("name"), str) else ""
    email = data.get("email", "").strip() if isinstance(data.get("email"), str) else ""
    message = data.get("message", "").strip() if isinstance(data.get("message"), str) else ""
    if not name or "@" not in email or not message:
        return jsonify({"error": "Name, valid email, and message are required"}), 400
    recipient = current_app.config.get("CONTACT_EMAIL")
    if not recipient:
        return jsonify({"error": "Contact email is not configured"}), 503
    delivered = send_email(
        recipient,
        f"Gatherly website message from {name[:100]}",
        f"From: {name[:100]} <{email[:255]}>\n\n{message[:5000]}",
    )
    if not delivered:
        return jsonify({"error": "Email delivery is unavailable. Please try again later."}), 503
    return jsonify({"message": "Your message has been sent"}), 201


@events_bp.get("/<int:event_id>")
def get_event(event_id):
    event = public_events_query().filter(Event.id == event_id).first()
    if not event:
        return jsonify({"error": "Event not found"}), 404
    result = event.to_dict()
    result["organizer_details"] = {
        "name": event.organizer.organization_name or event.organizer.full_name,
        "description": event.organizer.organization_description,
        "email": event.organizer.email,
        "phone": event.organizer.phone,
        "logo": event.organizer.organization_logo,
    }
    return jsonify({"event": result})


@events_bp.post("")
@require_roles("organizer")
def create_event():
    if g.current_user.approval_status != "approved":
        return jsonify({"error": "Organizer approval is required before creating events"}), 403
    data = request.get_json(silent=True) or {}
    try:
        values = event_fields(data)
    except (AttributeError, KeyError, TypeError, ValueError, InvalidOperation):
        return jsonify({"error": "Event details are invalid"}), 400
    status = data.get("save_as", "submit")
    if status not in ("draft", "submit"):
        return jsonify({"error": "save_as must be draft or submit"}), 400
    event = Event(
        organizer_id=g.current_user.id,
        approval_status="draft" if status == "draft" else "pending",
        **values,
    )
    db.session.add(event)
    log_activity(g.current_user, "event_created", f"Created event: {event.title}")
    db.session.commit()
    return jsonify({"event": event.to_dict(include_private=True)}), 201


@events_bp.get("/mine")
@require_roles("organizer")
def my_events():
    events = Event.query.filter_by(organizer_id=g.current_user.id).order_by(Event.created_at.desc()).all()
    return jsonify({"items": [event.to_dict(include_private=True) for event in events]})


@events_bp.get("/dashboard")
@require_roles("organizer")
def organizer_dashboard():
    events = Event.query.filter_by(organizer_id=g.current_user.id).all()
    ids = [event.id for event in events]
    registrations = Registration.query.filter(
        Registration.event_id.in_(ids) if ids else False,
    ).all()
    paid = sum(
        float(registration.payment.amount)
        for registration in registrations
        if registration.payment and registration.payment.payment_status == "paid"
    )
    attendance = Attendance.query.join(Ticket).join(Registration).filter(
        Registration.event_id.in_(ids) if ids else False
    ).count()
    return jsonify({
        "total_events": len(events),
        "pending_events": sum(item.approval_status == "pending" for item in events),
        "approved_events": sum(item.approval_status == "approved" for item in events),
        "rejected_events": sum(item.approval_status == "rejected" for item in events),
        "total_registrations": sum(item.status == "confirmed" for item in registrations),
        "total_attendees": attendance,
        "total_revenue": paid,
    })


@events_bp.get("/analytics")
@require_roles("organizer")
def organizer_analytics():
    event_ids = [event.id for event in Event.query.filter_by(organizer_id=g.current_user.id).all()]
    if not event_ids:
        return jsonify({"monthly_registrations": [], "event_registrations": [], "monthly_revenue": []})
    month = func.date_format(Registration.created_at, "%Y-%m") if db.engine.dialect.name == "mysql" else func.strftime("%Y-%m", Registration.created_at)
    registrations = db.session.query(
        month.label("month"), func.count(Registration.id)
    ).filter(Registration.event_id.in_(event_ids), Registration.status == "confirmed").group_by("month").order_by("month").all()
    per_event = db.session.query(
        Event.title, func.count(Registration.id)
    ).outerjoin(Registration).filter(Event.id.in_(event_ids)).group_by(Event.id, Event.title).all()
    revenue = db.session.query(
        month.label("month"), func.coalesce(func.sum(Payment.amount), 0)
    ).join(Registration, Registration.id == Payment.registration_id).filter(
        Registration.event_id.in_(event_ids), Payment.payment_status == "paid"
    ).group_by("month").order_by("month").all()
    return jsonify({
        "monthly_registrations": [{"month": key, "count": value} for key, value in registrations],
        "event_registrations": [{"event": key, "count": value} for key, value in per_event],
        "monthly_revenue": [{"month": key, "amount": float(value)} for key, value in revenue],
    })


@events_bp.put("/<int:event_id>")
@require_roles("organizer")
def update_event(event_id):
    event = db.session.get(Event, event_id)
    if not event or event.organizer_id != g.current_user.id:
        return jsonify({"error": "Event not found"}), 404
    if event.event_status == "cancelled":
        return jsonify({"error": "Cancelled events cannot be edited"}), 409
    data = request.get_json(silent=True) or {}
    try:
        values = event_fields(data, event)
    except (AttributeError, TypeError, ValueError, InvalidOperation, KeyError):
        db.session.rollback()
        return jsonify({"error": "Event details are invalid"}), 400
    for field, value in values.items():
        setattr(event, field, value)
    event.approval_status = "pending"
    event.rejection_reason = None
    notify_event_participants(
        event,
        f"Update to {event.title}",
        "Your event details changed. Review the latest event information in Gatherly.",
    )
    log_activity(g.current_user, "event_updated", f"Updated event: {event.title}")
    db.session.commit()
    return jsonify({"event": event.to_dict(include_private=True)})


@events_bp.put("/<int:event_id>/submit")
@require_roles("organizer")
def submit_event(event_id):
    event = db.session.get(Event, event_id)
    if not event or event.organizer_id != g.current_user.id:
        return jsonify({"error": "Event not found"}), 404
    if event.approval_status not in ("draft", "rejected"):
        return jsonify({"error": "Only drafts and rejected events can be resubmitted"}), 409
    if event.event_status != "active":
        return jsonify({"error": "Cancelled events cannot be submitted"}), 409
    event.approval_status = "pending"
    event.rejection_reason = None
    db.session.commit()
    return jsonify({"event": event.to_dict()})


@events_bp.post("/<int:event_id>/poster")
@require_roles("organizer")
def upload_event_poster(event_id):
    event = db.session.get(Event, event_id)
    if not event or event.organizer_id != g.current_user.id:
        return jsonify({"error": "Event not found"}), 404
    try:
        event.poster = upload_file(request.files.get("file"), "image")
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    event.approval_status = "pending" if event.approval_status == "approved" else event.approval_status
    db.session.commit()
    return jsonify({"event": event.to_dict(include_private=True)})


@events_bp.delete("/<int:event_id>")
@require_roles("organizer", "admin")
def delete_event(event_id):
    event = db.session.get(Event, event_id)
    if not event:
        return jsonify({"error": "Event not found"}), 404
    if g.current_user.role != "admin" and event.organizer_id != g.current_user.id:
        return jsonify({"error": "Event not found"}), 404
    if g.current_user.role != "admin" and event.approval_status not in ("draft", "rejected"):
        return jsonify({"error": "Only draft or rejected events can be deleted"}), 409
    db.session.delete(event)
    log_activity(g.current_user, "event_deleted", f"Deleted event: {event.title}")
    db.session.commit()
    return "", 204


@events_bp.post("/<int:event_id>/cancel")
@require_roles("organizer", "admin")
def cancel_event(event_id):
    event = db.session.get(Event, event_id)
    data = request.get_json(silent=True) or {}
    reason = data.get("reason", "").strip() if isinstance(data.get("reason"), str) else ""
    if not event:
        return jsonify({"error": "Event not found"}), 404
    if g.current_user.role == "organizer" and event.organizer_id != g.current_user.id:
        return jsonify({"error": "Event not found"}), 404
    if not reason:
        return jsonify({"error": "A cancellation reason is required"}), 400
    event.event_status = "cancelled"
    event.cancellation_reason = reason[:500]
    notify_event_participants(
        event,
        f"Cancelled: {event.title}",
        reason,
        "event_cancelled",
        include_pending=True,
    )
    pending = Registration.query.filter_by(
        event_id=event.id, status="pending_payment"
    ).all()
    for registration in pending:
        registration.status = "cancelled"
        registration.payment_status = "expired"
        if registration.payment and registration.payment.payment_status == "pending":
            registration.payment.payment_status = "expired"
    log_activity(g.current_user, "event_cancelled", f"Cancelled event: {event.title}")
    db.session.commit()
    return jsonify({"event": event.to_dict(include_private=True)})


@events_bp.get("/<int:event_id>/participants")
@require_roles("organizer", "admin")
def participants(event_id):
    event = db.session.get(Event, event_id)
    if not event:
        return jsonify({"error": "Event not found"}), 404
    if g.current_user.role == "organizer" and event.organizer_id != g.current_user.id:
        return jsonify({"error": "Event not found"}), 404
    query = Registration.query.join(User).filter(Registration.event_id == event.id)
    search = request.args.get("search", "").strip()
    if search:
        query = query.filter(or_(User.full_name.ilike(f"%{search}%"), User.email.ilike(f"%{search}%")))
    status = request.args.get("status")
    if status in ("confirmed", "cancelled", "pending_payment", "expired"):
        query = query.filter(Registration.status == status)
    entries = query.order_by(Registration.created_at.desc()).limit(500).all()
    return jsonify({"items": [{
        "id": item.id,
        "full_name": item.user.full_name,
        "email": item.user.email,
        "phone": item.user.phone,
        "registration_number": item.registration_number,
        "registration_date": utc_iso(item.created_at),
        "payment_status": item.payment_status,
        "registration_status": item.status,
        "attendance_status": "checked_in" if item.ticket and item.ticket.attendance else "not_checked_in",
    } for item in entries]})


@events_bp.get("/<int:event_id>/participants.csv")
@require_roles("organizer", "admin")
def export_participants(event_id):
    event = db.session.get(Event, event_id)
    if not event or (g.current_user.role == "organizer" and event.organizer_id != g.current_user.id):
        return jsonify({"error": "Event not found"}), 404
    rows = Registration.query.join(User).filter(Registration.event_id == event.id).order_by(Registration.created_at.asc()).all()
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["Name", "Email", "Phone", "Registration ID", "Registration date", "Registration status", "Payment status", "Attendance"])
    for item in rows:
        writer.writerow([
            item.user.full_name, item.user.email, item.user.phone or "",
            item.registration_number, utc_iso(item.created_at), item.status,
            item.payment_status,
            "checked_in" if item.ticket and item.ticket.attendance else "not_checked_in",
        ])
    response = make_response(output.getvalue())
    response.headers["Content-Type"] = "text/csv; charset=utf-8"
    response.headers["Content-Disposition"] = f'attachment; filename="event-{event.id}-participants.csv"'
    return response


@events_bp.get("/<int:event_id>/announcements")
@require_roles("organizer", "admin")
def event_announcements(event_id):
    event = db.session.get(Event, event_id)
    if not event or (g.current_user.role == "organizer" and event.organizer_id != g.current_user.id):
        return jsonify({"error": "Event not found"}), 404
    entries = Announcement.query.filter_by(event_id=event.id).order_by(Announcement.created_at.desc()).all()
    return jsonify({"items": [{
        "id": item.id,
        "title": item.title,
        "message": item.message,
        "created_at": utc_iso(item.created_at),
    } for item in entries]})


@events_bp.post("/<int:event_id>/announcements")
@require_roles("organizer", "admin")
def send_announcement(event_id):
    event = db.session.get(Event, event_id)
    data = request.get_json(silent=True) or {}
    title = data.get("title", "").strip() if isinstance(data.get("title"), str) else ""
    message = data.get("message", "").strip() if isinstance(data.get("message"), str) else ""
    if not event or (g.current_user.role == "organizer" and event.organizer_id != g.current_user.id):
        return jsonify({"error": "Event not found"}), 404
    if not title or not message:
        return jsonify({"error": "Announcement title and message are required"}), 400
    db.session.add(Announcement(
        event_id=event.id,
        organizer_id=event.organizer_id,
        title=title[:160],
        message=message,
    ))
    notify_event_participants(event, title[:160], message, "announcement")
    db.session.commit()
    return jsonify({"message": "Announcement sent to registered participants"}), 201


@events_bp.get("/<int:event_id>/attendance")
@require_roles("organizer", "admin")
def event_attendance(event_id):
    event = db.session.get(Event, event_id)
    if not event or (g.current_user.role == "organizer" and event.organizer_id != g.current_user.id):
        return jsonify({"error": "Event not found"}), 404
    checked_in = Attendance.query.join(Ticket).join(Registration).filter(Registration.event_id == event.id).order_by(Attendance.check_in_time.desc()).all()
    return jsonify({"items": [{
        "participant": item.ticket.registration.user.full_name,
        "email": item.ticket.registration.user.email,
        "registration_number": item.ticket.registration.registration_number,
        "check_in_time": utc_iso(item.check_in_time),
    } for item in checked_in]})
