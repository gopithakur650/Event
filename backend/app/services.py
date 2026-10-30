import logging
import os
import secrets
from datetime import timedelta
from io import BytesIO

import qrcode
from flask import current_app, url_for
from flask_mail import Message
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from werkzeug.utils import secure_filename

from app.models import ActivityLog, Notification, Ticket, utcnow
from extensions import db, mail

logger = logging.getLogger(__name__)
ALLOWED_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
ALLOWED_DOCUMENT_EXTENSIONS = {"pdf", "jpg", "jpeg", "png"}


def create_ticket(registration):
    ticket = Ticket.query.filter_by(registration_id=registration.id).first()
    if ticket:
        ticket.status = "valid"
        ticket.qr_token = secrets.token_urlsafe(32)
        return ticket
    ticket = Ticket(
        registration_id=registration.id,
        ticket_number=f"TKT-{secrets.token_hex(8).upper()}",
        qr_token=secrets.token_urlsafe(32),
    )
    db.session.add(ticket)
    return ticket


def notify_user(user_id, title, message, notification_type="general"):
    db.session.add(Notification(
        user_id=user_id,
        title=title,
        message=message,
        notification_type=notification_type,
    ))


def notify_event_participants(
    event, title, message, notification_type="event_update", include_pending=False
):
    from app.models import Registration

    statuses = ("confirmed", "pending_payment") if include_pending else ("confirmed",)
    registrations = Registration.query.filter(
        Registration.event_id == event.id,
        Registration.status.in_(statuses),
    ).all()
    for registration in registrations:
        notify_user(registration.user_id, title, message, notification_type)
        send_email(
            registration.user.email,
            title,
            message,
        )


def log_activity(actor, action, description):
    if not actor:
        return
    db.session.add(ActivityLog(
        actor_id=actor.id,
        actor_role=actor.role,
        action=action,
        description=description,
    ))


def send_email(recipient, subject, body):
    if not current_app.config.get("MAIL_SERVER") or not current_app.config.get("MAIL_DEFAULT_SENDER"):
        logger.info("Email not sent because SMTP is not configured (subject=%s)", subject)
        return False
    try:
        mail.send(Message(subject=subject, recipients=[recipient], body=body))
    except Exception:
        logger.exception("Email delivery failed for configured SMTP provider")
        return False
    return True


def upload_file(file, category):
    if not file or not file.filename:
        raise ValueError("Choose a file to upload")
    filename = secure_filename(file.filename)
    if "." not in filename:
        raise ValueError("File type is not allowed")
    extension = filename.rsplit(".", 1)[1].lower()
    allowed = ALLOWED_IMAGE_EXTENSIONS if category == "image" else ALLOWED_DOCUMENT_EXTENSIONS
    if extension not in allowed:
        raise ValueError("This file type is not allowed")
    contents = file.read(current_app.config["MAX_UPLOAD_SIZE"] + 1)
    if len(contents) > current_app.config["MAX_UPLOAD_SIZE"]:
        raise ValueError("File must be 5 MB or smaller")
    if category == "image":
        from PIL import Image, UnidentifiedImageError

        try:
            image = Image.open(BytesIO(contents))
            actual_extension = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}.get(image.format)
            if actual_extension != extension:
                raise ValueError("The uploaded image extension does not match its contents")
            image.verify()
        except ValueError:
            raise
        except (UnidentifiedImageError, OSError):
            raise ValueError("The uploaded image is invalid") from None
    stored_name = f"{'images' if category == 'image' else 'documents'}/{secrets.token_hex(16)}.{extension}"
    directory = os.path.abspath(os.path.join(
        current_app.root_path, "..", current_app.config["UPLOAD_FOLDER"]
    ))
    destination_path = os.path.join(directory, *stored_name.split("/"))
    os.makedirs(os.path.dirname(destination_path), exist_ok=True)
    with open(destination_path, "xb") as destination:
        destination.write(contents)
    return stored_name


def qr_png(ticket):
    output = BytesIO()
    qrcode.make(ticket.qr_token).save(output, format="PNG")
    output.seek(0)
    return output


def ticket_pdf(ticket):
    registration = ticket.registration
    event = registration.event
    output = BytesIO()
    pdf = canvas.Canvas(output, pagesize=letter)
    pdf.setTitle(f"Gatherly ticket {ticket.ticket_number}")
    pdf.setFont("Helvetica-Bold", 22)
    pdf.drawString(55, 745, "Gatherly event ticket")
    pdf.setFont("Helvetica", 12)
    lines = (
        ("Participant", registration.user.full_name),
        ("Event", event.title),
        ("Registration ID", registration.registration_number),
        ("Ticket ID", ticket.ticket_number),
        ("Date", event.start_at.strftime("%B %d, %Y at %I:%M %p UTC")),
        ("Venue", event.venue or "Online"),
        ("Status", registration.status.title()),
    )
    y = 690
    for label, value in lines:
        pdf.setFont("Helvetica-Bold", 10)
        pdf.drawString(55, y, f"{label}:")
        pdf.setFont("Helvetica", 11)
        pdf.drawString(155, y, value[:75])
        y -= 28
    qr_image = qr_png(ticket)
    pdf.drawImage(ImageReader(qr_image), 390, 505, width=145, height=145)
    pdf.setFont("Helvetica", 9)
    pdf.drawString(55, 480, "Present this QR code at event check-in. Each ticket can be used once.")
    pdf.save()
    output.seek(0)
    return output


def expire_pending_registration(registration):
    if registration.pending_expires_at and registration.pending_expires_at <= utcnow():
        registration.status = "expired"
        registration.payment_status = "expired"
        return True
    return False
