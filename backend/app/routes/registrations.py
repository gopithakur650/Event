import hashlib
import hmac
import logging
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from flask import Blueprint, current_app, g, jsonify, make_response, request, send_file
from sqlalchemy.exc import IntegrityError

from app.models import (
    Attendance,
    Event,
    Feedback,
    Notification,
    Payment,
    Registration,
    Ticket,
    utc_iso,
    utcnow,
)
from app.payment_gateway import PaymentProviderError, RazorpayGateway
from app.routes.common import require_roles
from app.services import (
    create_ticket,
    log_activity,
    notify_user,
    qr_png,
    send_email,
    ticket_pdf,
)
from extensions import db, limiter

logger = logging.getLogger(__name__)
registrations_bp = Blueprint("registrations", __name__, url_prefix="")
PENDING_PAYMENT_TTL = timedelta(minutes=15)


def payment_client():
    if not current_app.config.get("RAZORPAY_KEY_ID") or not current_app.config.get("RAZORPAY_KEY_SECRET"):
        return None
    return RazorpayGateway()


def checkout_details(payment):
    return {
        "registration_id": payment.registration_id,
        "registration_number": payment.registration.registration_number,
        "payment_id": payment.id,
        "order_id": payment.gateway_order_id,
        "amount": int(payment.amount * 100),
        "currency": payment.currency,
        "key_id": current_app.config["RAZORPAY_KEY_ID"],
        "prefill": {
            "name": payment.registration.user.full_name,
            "email": payment.registration.user.email,
            "contact": payment.registration.user.phone or "",
        },
    }


def confirm_payment(payment, transaction_id, method=None, gateway_reference=None):
    if payment.payment_status == "paid":
        if payment.transaction_id != transaction_id:
            raise ValueError("Payment has already been completed with a different transaction")
        return False
    if payment.payment_status != "pending":
        raise ValueError("This payment is no longer pending")
    payment.payment_status = "paid"
    payment.transaction_id = transaction_id
    payment.payment_method = method
    payment.gateway_reference = gateway_reference
    payment.payment_date = utcnow()
    registration = payment.registration
    registration.status = "confirmed"
    registration.payment_status = "paid"
    registration.pending_expires_at = None
    ticket = create_ticket(registration)
    notify_user(
        registration.user_id,
        "Payment confirmed",
        f"Your payment for {registration.event.title} is confirmed. Your ticket is ready.",
        "payment_confirmation",
    )
    log_activity(registration.user, "payment_confirmed", f"Payment confirmed for {registration.registration_number}")
    return ticket


def refund_expired_payment(client, payment, gateway_payment):
    registration = payment.registration
    payment_id = gateway_payment["id"]
    payment.transaction_id = payment_id
    payment.payment_method = gateway_payment.get("method")
    payment.payment_date = utcnow()
    payment.payment_status = "refund_pending"
    registration.status = "expired"
    registration.payment_status = "refund_pending"
    db.session.commit()
    try:
        if not client:
            raise PaymentProviderError("Razorpay credentials are not configured")
        refund = client.refund_payment(payment_id, int(payment.amount * 100))
    except PaymentProviderError:
        logger.exception("Refund request failed for a payment captured after its reservation expired")
        notify_user(
            registration.user_id,
            "Payment needs attention",
            "Your event reservation expired before payment completed. The payment provider did not confirm an automatic refund; contact support.",
            "payment_refund",
        )
        db.session.commit()
        return jsonify({"error": "The reservation expired. Contact support to resolve the captured payment."}), 409
    payment.refund_reference = refund.get("id")
    if refund.get("status") == "processed":
        payment.payment_status = "refunded"
        payment.refunded_at = utcnow()
        registration.payment_status = "refunded"
    notify_user(
        registration.user_id,
        "Reservation expired",
        "Your reservation expired before payment completed. A refund was requested from the payment provider.",
        "payment_refund",
    )
    db.session.commit()
    return jsonify({"error": "The reservation expired. A refund was requested; the event ticket was not issued."}), 409


@registrations_bp.post("/registrations")
@limiter.limit("20 per minute")
@require_roles("user")
def register_for_event():
    data = request.get_json(silent=True) or {}
    event_id = data.get("event_id")
    event = db.session.get(Event, event_id) if isinstance(event_id, int) and not isinstance(event_id, bool) else None
    now = utcnow()
    if not event or event.approval_status != "approved" or event.event_status != "active":
        return jsonify({"error": "Event is not available for registration"}), 404
    if event.registration_start > now or event.registration_deadline <= now or event.start_at <= now:
        return jsonify({"error": "Registration is not open"}), 409
    existing_checkout = None
    free_registration = False
    registration = None
    payment = None
    try:
        with db.session.begin_nested():
            db.session.query(Event).filter(Event.id == event.id).with_for_update().one()
            existing = Registration.query.filter_by(
                user_id=g.current_user.id, event_id=event.id
            ).first()
            if existing and existing.status == "pending_payment":
                if existing.pending_expires_at and existing.pending_expires_at > now:
                    prior_payment = Payment.query.filter_by(registration_id=existing.id).first()
                    if prior_payment and prior_payment.payment_status == "pending":
                        existing_checkout = prior_payment
                if existing_checkout is None:
                    existing.status = "expired"
                    existing.payment_status = "expired"
            if existing and existing.status == "confirmed":
                return jsonify({"error": "You are already registered for this event"}), 409
            if existing_checkout is None:
                occupied = Registration.query.filter(
                    Registration.event_id == event.id,
                    Registration.status == "confirmed",
                ).count() + Registration.query.filter(
                    Registration.event_id == event.id,
                    Registration.status == "pending_payment",
                    Registration.pending_expires_at > now,
                ).count()
                if occupied >= event.capacity:
                    return jsonify({"error": "Event is full"}), 409
                if event.fee > 0 and not payment_client():
                    return jsonify({"error": "Paid registration is unavailable because the Razorpay gateway is not configured"}), 503

                if event.fee == 0:
                    if existing:
                        registration = existing
                        registration.status = "confirmed"
                        registration.payment_status = "not_required"
                    else:
                        registration = Registration(
                            user_id=g.current_user.id,
                            event_id=event.id,
                            registration_number=f"REG-{uuid4().hex[:16].upper()}",
                            payment_status="not_required",
                        )
                        db.session.add(registration)
                    db.session.flush()
                    create_ticket(registration)
                    notify_user(
                        g.current_user.id,
                        "Registration confirmed",
                        f"Your registration for {event.title} is confirmed.",
                        "registration_confirmation",
                    )
                    log_activity(g.current_user, "registration_confirmed", f"Registered for {event.title}")
                    free_registration = True
                else:
                    if existing:
                        registration = existing
                        registration.status = "pending_payment"
                        registration.payment_status = "pending"
                        registration.pending_expires_at = now + PENDING_PAYMENT_TTL
                    else:
                        registration = Registration(
                            user_id=g.current_user.id,
                            event_id=event.id,
                            registration_number=f"REG-{uuid4().hex[:16].upper()}",
                            status="pending_payment",
                            payment_status="pending",
                            pending_expires_at=now + PENDING_PAYMENT_TTL,
                        )
                        db.session.add(registration)
                    db.session.flush()
                    payment = Payment.query.filter_by(registration_id=registration.id).first()
                    if not payment:
                        payment = Payment(
                            registration_id=registration.id,
                            amount=event.fee,
                            currency="INR",
                            payment_status="pending",
                        )
                        db.session.add(payment)
                    else:
                        payment.amount = event.fee
                        payment.payment_status = "pending"
                        payment.gateway_order_id = None
                        payment.transaction_id = None
                    db.session.flush()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "You already have an active registration for this event"}), 409

    if existing_checkout:
        return jsonify({"checkout": checkout_details(existing_checkout)}), 200
    db.session.commit()
    if free_registration:
        send_email(
            registration.user.email,
            f"Registration confirmed: {event.title}",
            f"Your registration is confirmed. Registration number: {registration.registration_number}",
        )
        return jsonify({"registration": registration.to_dict()}), 201

    client = payment_client()
    try:
        order = client.create_order(
            amount=int(payment.amount * 100),
            currency=payment.currency,
            receipt=registration.registration_number,
            notes={"event_id": str(event.id), "registration_id": str(registration.id)},
            expire_by=int(registration.pending_expires_at.replace(tzinfo=timezone.utc).timestamp()),
        )
    except PaymentProviderError:
        logger.exception("Razorpay order creation failed")
        payment.payment_status = "failed"
        registration.payment_status = "failed"
        registration.status = "expired"
        db.session.commit()
        return jsonify({"error": "Payment provider could not create an order. Please try again."}), 502
    if not isinstance(order.get("id"), str):
        payment.payment_status = "failed"
        registration.payment_status = "failed"
        registration.status = "expired"
        db.session.commit()
        return jsonify({"error": "Payment provider returned an invalid order"}), 502
    payment.gateway_order_id = order["id"]
    db.session.commit()
    return jsonify({"checkout": checkout_details(payment)}), 201


@registrations_bp.post("/payments/verify")
@require_roles("user")
def verify_payment():
    data = request.get_json(silent=True) or {}
    order_id = data.get("razorpay_order_id")
    payment_id = data.get("razorpay_payment_id")
    signature = data.get("razorpay_signature")
    payment = Payment.query.filter_by(gateway_order_id=order_id).first() if isinstance(order_id, str) else None
    if not payment or payment.registration.user_id != g.current_user.id:
        return jsonify({"error": "Payment order not found"}), 404
    if not all(isinstance(value, str) for value in (payment_id, signature)):
        return jsonify({"error": "Payment verification details are invalid"}), 400
    client = payment_client()
    if not client:
        return jsonify({"error": "Payment verification is unavailable"}), 503
    try:
        if not client.verify_payment_signature(order_id, payment_id, signature):
            return jsonify({"error": "Payment signature is invalid"}), 400
        gateway_payment = client.fetch_payment(payment_id)
        expected_amount = int(payment.amount * 100)
        if gateway_payment.get("order_id") != order_id or gateway_payment.get("amount") != expected_amount:
            return jsonify({"error": "Payment details do not match this registration"}), 400
        if gateway_payment.get("status") != "captured":
            return jsonify({"error": "Payment has not been captured"}), 409
        if payment.payment_status != "paid" and (
            payment.registration.status != "pending_payment"
            or not payment.registration.pending_expires_at
            or payment.registration.pending_expires_at <= utcnow()
            or payment.registration.event.event_status != "active"
        ):
            return refund_expired_payment(client, payment, gateway_payment)
        confirm_payment(
            payment,
            payment_id,
            gateway_payment.get("method"),
            gateway_payment.get("id"),
        )
        db.session.commit()
    except ValueError as error:
        db.session.rollback()
        return jsonify({"error": str(error)}), 409
    except PaymentProviderError:
        db.session.rollback()
        logger.exception("Razorpay payment verification failed")
        return jsonify({"error": "Payment verification could not be completed"}), 502
    send_email(
        g.current_user.email,
        "Gatherly payment confirmed",
        f"Your payment for {payment.registration.event.title} is confirmed. Registration: {payment.registration.registration_number}",
    )
    return jsonify({
        "message": "Payment verified and ticket issued",
        "registration": payment.registration.to_dict(),
    })


@registrations_bp.post("/payments/webhook")
@limiter.limit("60 per minute")
def payment_webhook():
    secret = current_app.config.get("RAZORPAY_WEBHOOK_SECRET")
    signature = request.headers.get("X-Razorpay-Signature", "")
    body = request.get_data()
    if not secret:
        return jsonify({"error": "Payment webhook is not configured"}), 503
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        return jsonify({"error": "Webhook signature is invalid"}), 400
    payload = request.get_json(silent=True) or {}
    event_type = payload.get("event")
    details = payload.get("payload", {})
    if not isinstance(details, dict):
        return jsonify({"error": "Webhook payload is invalid"}), 400
    payment_entity = details.get("payment", {}).get("entity", {})
    refund_entity = details.get("refund", {}).get("entity", {})
    if event_type == "refund.processed":
        payment = Payment.query.filter_by(transaction_id=refund_entity.get("payment_id")).first()
        entity = refund_entity
    elif event_type in ("payment.captured", "payment.failed"):
        entity = payment_entity
        payment = Payment.query.filter_by(gateway_order_id=entity.get("order_id")).first()
    else:
        return jsonify({"message": "Webhook event ignored"})
    if not payment:
        logger.warning("Verified Razorpay webhook refers to an unknown order")
        return jsonify({"error": "Payment order not found"}), 404
    try:
        if event_type == "payment.captured":
            if entity.get("amount") != int(payment.amount * 100):
                return jsonify({"error": "Webhook payment amount does not match"}), 400
            if payment.payment_status != "paid" and (
                payment.registration.status != "pending_payment"
                or not payment.registration.pending_expires_at
                or payment.registration.pending_expires_at <= utcnow()
                or payment.registration.event.event_status != "active"
            ):
                refund_expired_payment(payment_client(), payment, entity)
                return jsonify({"message": "Expired reservation payment refund handled"})
            confirm_payment(payment, entity.get("id"), entity.get("method"), entity.get("id"))
        elif event_type == "payment.failed" and payment.payment_status == "pending":
            payment.payment_status = "failed"
            payment.registration.payment_status = "failed"
            payment.registration.status = "expired"
        elif event_type == "refund.processed" and payment.payment_status == "refund_pending":
            payment.payment_status = "refunded"
            payment.refund_reference = entity.get("id")
            payment.refunded_at = utcnow()
            payment.registration.payment_status = "refunded"
        db.session.commit()
    except ValueError:
        db.session.rollback()
        logger.exception("Verified payment webhook conflicted with existing payment state")
        return jsonify({"error": "Payment state could not be applied"}), 409
    return jsonify({"message": "Webhook processed"})


@registrations_bp.get("/registrations/my")
@require_roles("user")
def my_registrations():
    registrations = Registration.query.filter_by(user_id=g.current_user.id).order_by(Registration.created_at.desc()).all()
    return jsonify({"items": [item.to_dict() for item in registrations]})


@registrations_bp.get("/registrations/<int:registration_id>")
@require_roles("user", "organizer", "admin")
def get_registration(registration_id):
    registration = db.session.get(Registration, registration_id)
    if not registration:
        return jsonify({"error": "Registration not found"}), 404
    if g.current_user.role == "user" and registration.user_id != g.current_user.id:
        return jsonify({"error": "Registration not found"}), 404
    if g.current_user.role == "organizer" and registration.event.organizer_id != g.current_user.id:
        return jsonify({"error": "Registration not found"}), 404
    return jsonify({"registration": registration.to_dict()})


@registrations_bp.delete("/registrations/<int:registration_id>")
@require_roles("user")
def cancel_registration(registration_id):
    registration = db.session.get(Registration, registration_id)
    if not registration or registration.user_id != g.current_user.id:
        return jsonify({"error": "Registration not found"}), 404
    if registration.status != "confirmed" or registration.event.start_at <= utcnow():
        return jsonify({"error": "This registration can no longer be cancelled"}), 409
    registration.status = "cancelled"
    ticket = Ticket.query.filter_by(registration_id=registration.id).first()
    if ticket:
        ticket.status = "cancelled"
    notify_user(
        g.current_user.id,
        "Registration cancelled",
        f"Your registration for {registration.event.title} was cancelled. Contact the organizer regarding any payment refund.",
        "registration_cancelled",
    )
    db.session.commit()
    return "", 204


@registrations_bp.get("/tickets/<int:registration_id>")
@require_roles("user", "organizer", "admin")
def get_ticket(registration_id):
    registration = db.session.get(Registration, registration_id)
    if not registration:
        return jsonify({"error": "Ticket not found"}), 404
    if g.current_user.role == "user" and registration.user_id != g.current_user.id:
        return jsonify({"error": "Ticket not found"}), 404
    if g.current_user.role == "organizer" and registration.event.organizer_id != g.current_user.id:
        return jsonify({"error": "Ticket not found"}), 404
    ticket = Ticket.query.filter_by(registration_id=registration.id).first()
    if not ticket or registration.status != "confirmed":
        return jsonify({"error": "Ticket not found"}), 404
    return jsonify({
        "ticket": ticket.to_dict(),
        "registration": registration.to_dict(),
    })


@registrations_bp.get("/tickets/<int:registration_id>/qr")
@require_roles("user", "organizer", "admin")
def ticket_qr(registration_id):
    ticket = authorized_ticket(registration_id)
    if not ticket:
        return jsonify({"error": "Ticket not found"}), 404
    response = make_response(qr_png(ticket).getvalue())
    response.headers["Content-Type"] = "image/png"
    response.headers["Cache-Control"] = "private, no-store"
    return response


@registrations_bp.get("/tickets/<int:registration_id>/download")
@require_roles("user", "organizer", "admin")
def download_ticket(registration_id):
    ticket = authorized_ticket(registration_id)
    if not ticket:
        return jsonify({"error": "Ticket not found"}), 404
    return send_file(
        ticket_pdf(ticket),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"gatherly-{ticket.ticket_number}.pdf",
    )


def authorized_ticket(registration_id):
    registration = db.session.get(Registration, registration_id)
    if not registration or registration.status != "confirmed":
        return None
    if g.current_user.role == "user" and registration.user_id != g.current_user.id:
        return None
    if g.current_user.role == "organizer" and registration.event.organizer_id != g.current_user.id:
        return None
    return Ticket.query.filter_by(registration_id=registration.id, status="valid").first()


@registrations_bp.post("/attendance/verify")
@require_roles("organizer", "admin")
def verify_ticket():
    data = request.get_json(silent=True) or {}
    token = data.get("qr_token")
    event_id = data.get("event_id")
    ticket = Ticket.query.filter_by(qr_token=token).first() if isinstance(token, str) else None
    if not ticket or ticket.status != "valid":
        return jsonify({"error": "Ticket is invalid"}), 404
    registration = db.session.get(Registration, ticket.registration_id)
    if event_id is not None and event_id != registration.event_id:
        return jsonify({"error": "Ticket does not belong to the selected event"}), 409
    if registration.status != "confirmed" or registration.payment_status not in ("not_required", "paid"):
        return jsonify({"error": "Registration or payment is not valid"}), 409
    if g.current_user.role == "organizer" and registration.event.organizer_id != g.current_user.id:
        return jsonify({"error": "Ticket does not belong to your event"}), 403
    if Attendance.query.filter_by(ticket_id=ticket.id).first():
        return jsonify({"error": "Ticket has already been checked in"}), 409
    try:
        db.session.add(Attendance(ticket_id=ticket.id, checked_by=g.current_user.id))
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "Ticket has already been checked in"}), 409
    return jsonify({
        "message": "Attendance recorded",
        "participant": registration.user.full_name,
        "event": registration.event.title,
        "registration_number": registration.registration_number,
    })


@registrations_bp.get("/notifications")
@require_roles("user", "organizer", "admin")
def notifications():
    items = Notification.query.filter_by(user_id=g.current_user.id).order_by(Notification.created_at.desc()).limit(100).all()
    return jsonify({"items": [item.to_dict() for item in items]})


@registrations_bp.post("/feedback")
@require_roles("user")
def submit_feedback():
    data = request.get_json(silent=True) or {}
    event_id = data.get("event_id")
    rating = data.get("rating")
    event = db.session.get(Event, event_id) if isinstance(event_id, int) and not isinstance(event_id, bool) else None
    if not event or not isinstance(rating, int) or isinstance(rating, bool) or not 1 <= rating <= 5:
        return jsonify({"error": "Valid event and rating are required"}), 400
    if event.event_status == "cancelled" or event.end_at > utcnow():
        return jsonify({"error": "Feedback is available only after a completed event"}), 409
    registration = Registration.query.filter_by(
        user_id=g.current_user.id, event_id=event.id, status="confirmed"
    ).first()
    if not registration:
        return jsonify({"error": "Only registered participants can submit feedback"}), 403
    comments = data.get("comments", "")
    suggestions = data.get("suggestions", "")
    if not isinstance(comments, str) or not isinstance(suggestions, str):
        return jsonify({"error": "Comments and suggestions must be text"}), 400
    feedback = Feedback(
        user_id=g.current_user.id,
        event_id=event.id,
        rating=rating,
        comments=comments.strip(),
        suggestions=suggestions.strip(),
    )
    db.session.add(feedback)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "Feedback has already been submitted"}), 409
    return jsonify({"message": "Feedback submitted"}), 201


@registrations_bp.get("/feedback/<int:event_id>")
def event_feedback(event_id):
    event = db.session.get(Event, event_id)
    if not event or event.approval_status != "approved":
        return jsonify({"error": "Event not found"}), 404
    entries = Feedback.query.filter_by(event_id=event.id).order_by(Feedback.created_at.desc()).limit(100).all()
    return jsonify({"items": [{
        "rating": item.rating,
        "comments": item.comments,
        "suggestions": item.suggestions,
        "created_at": utc_iso(item.created_at),
    } for item in entries]})


@registrations_bp.put("/notifications/<int:notification_id>/read")
@require_roles("user", "organizer", "admin")
def mark_notification_read(notification_id):
    item = db.session.get(Notification, notification_id)
    if not item or item.user_id != g.current_user.id:
        return jsonify({"error": "Notification not found"}), 404
    item.is_read = True
    db.session.commit()
    return jsonify({"message": "Notification marked as read"})


@registrations_bp.get("/organizer/participants/<int:event_id>")
@require_roles("organizer", "admin")
def organizer_participants(event_id):
    from app.routes.events import participants as event_participants

    return event_participants(event_id)
