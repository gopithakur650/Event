from datetime import datetime, timezone

from sqlalchemy import or_
from werkzeug.security import check_password_hash, generate_password_hash

from extensions import db


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def utc_iso(value):
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    phone = db.Column(db.String(32))
    password_hash = db.Column(db.String(255), nullable=False)
    auth_version = db.Column(db.Integer, nullable=False, default=1)
    role = db.Column(db.String(20), nullable=False, default="user", index=True)
    college_name = db.Column(db.String(180))
    department = db.Column(db.String(120))
    student_id = db.Column(db.String(80))
    profile_image = db.Column(db.String(255))
    organization_name = db.Column(db.String(160))
    organization_description = db.Column(db.Text)
    organization_address = db.Column(db.String(255))
    organization_logo = db.Column(db.String(255))
    supporting_document = db.Column(db.String(255))
    account_status = db.Column(db.String(20), nullable=False, default="active", index=True)
    approval_status = db.Column(db.String(20), nullable=False, default="approved", index=True)
    rejection_reason = db.Column(db.String(500))
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {
            "id": self.id,
            "full_name": self.full_name,
            "email": self.email,
            "phone": self.phone,
            "role": self.role,
            "college_name": self.college_name,
            "department": self.department,
            "student_id": self.student_id,
            "profile_image": self.profile_image,
            "organization_name": self.organization_name,
            "organization_description": self.organization_description,
            "organization_address": self.organization_address,
            "organization_logo": self.organization_logo,
            "supporting_document": self.supporting_document,
            "account_status": self.account_status,
            "approval_status": self.approval_status,
            "rejection_reason": self.rejection_reason,
            "created_at": utc_iso(self.created_at),
        }


class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    description = db.Column(db.String(255))
    active = db.Column(db.Boolean, nullable=False, default=True)

    def to_dict(self):
        return {"id": self.id, "name": self.name, "description": self.description}


class Event(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    organizer_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="RESTRICT"), nullable=False, index=True)
    category_id = db.Column(db.Integer, db.ForeignKey("category.id", ondelete="RESTRICT"), nullable=False, index=True)
    title = db.Column(db.String(180), nullable=False, index=True)
    description = db.Column(db.Text, nullable=False)
    poster = db.Column(db.String(255))
    event_type = db.Column(db.String(20), nullable=False, default="offline")
    start_at = db.Column(db.DateTime(timezone=True), nullable=False, index=True)
    end_at = db.Column(db.DateTime(timezone=True), nullable=False)
    registration_start = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    registration_deadline = db.Column(db.DateTime(timezone=True), nullable=False)
    venue = db.Column(db.String(180), nullable=False, default="")
    address = db.Column(db.String(255), nullable=False, default="")
    city = db.Column(db.String(100))
    state = db.Column(db.String(100))
    postal_code = db.Column(db.String(20))
    online_meeting_link = db.Column(db.String(500))
    capacity = db.Column(db.Integer, nullable=False)
    fee = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    eligibility = db.Column(db.Text)
    age_restriction = db.Column(db.String(100))
    department_restriction = db.Column(db.String(255))
    event_rules = db.Column(db.Text)
    required_materials = db.Column(db.Text)
    contact_person = db.Column(db.String(120))
    contact_email = db.Column(db.String(255))
    contact_phone = db.Column(db.String(32))
    website = db.Column(db.String(500))
    approval_status = db.Column(db.String(20), nullable=False, default="pending", index=True)
    event_status = db.Column(db.String(20), nullable=False, default="active", index=True)
    rejection_reason = db.Column(db.String(500))
    cancellation_reason = db.Column(db.String(500))
    reminder_sent = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)
    organizer = db.relationship("User", backref="events")
    category = db.relationship("Category")

    def to_dict(self, include_private=False):
        now = utcnow()
        registrations = Registration.query.filter(
            Registration.event_id == self.id,
            Registration.status.in_(("confirmed", "pending_payment")),
            or_(Registration.pending_expires_at.is_(None), Registration.pending_expires_at > now),
        ).count()
        result = {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "poster": self.poster,
            "event_type": self.event_type,
            "start_at": utc_iso(self.start_at),
            "end_at": utc_iso(self.end_at),
            "registration_start": utc_iso(self.registration_start),
            "registration_deadline": utc_iso(self.registration_deadline),
            "venue": self.venue,
            "address": self.address,
            "city": self.city,
            "state": self.state,
            "postal_code": self.postal_code,
            "online_meeting_link": self.online_meeting_link,
            "capacity": self.capacity,
            "available_seats": max(0, self.capacity - registrations),
            "fee": float(self.fee),
            "eligibility": self.eligibility,
            "age_restriction": self.age_restriction,
            "department_restriction": self.department_restriction,
            "event_rules": self.event_rules,
            "required_materials": self.required_materials,
            "contact_person": self.contact_person,
            "contact_email": self.contact_email,
            "contact_phone": self.contact_phone,
            "website": self.website,
            "approval_status": self.approval_status,
            "event_status": self.event_status,
            "category": self.category.to_dict() if self.category else None,
            "organizer": self.organizer.organization_name or self.organizer.full_name if self.organizer else None,
            "organizer_id": self.organizer_id,
            "created_at": utc_iso(self.created_at),
        }
        if include_private:
            result.update({
                "rejection_reason": self.rejection_reason,
                "cancellation_reason": self.cancellation_reason,
            })
        return result


class Registration(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)
    event_id = db.Column(db.Integer, db.ForeignKey("event.id", ondelete="CASCADE"), nullable=False, index=True)
    registration_number = db.Column(db.String(36), unique=True, nullable=False)
    status = db.Column(db.String(24), nullable=False, default="confirmed", index=True)
    payment_status = db.Column(db.String(20), nullable=False, default="not_required")
    pending_expires_at = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    __table_args__ = (
        db.UniqueConstraint("user_id", "event_id", name="uq_registration_user_event"),
    )
    user = db.relationship("User")
    event = db.relationship("Event", backref="registrations")

    def to_dict(self):
        ticket = Ticket.query.filter_by(registration_id=self.id).first()
        return {
            "id": self.id,
            "registration_number": self.registration_number,
            "status": self.status,
            "payment_status": self.payment_status,
            "created_at": utc_iso(self.created_at),
            "event": self.event.to_dict(),
            "ticket": ticket.to_dict(include_token=False) if ticket else None,
        }


class Payment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    registration_id = db.Column(db.Integer, db.ForeignKey("registration.id", ondelete="CASCADE"), unique=True, nullable=False)
    transaction_id = db.Column(db.String(120), unique=True)
    gateway_order_id = db.Column(db.String(120), unique=True)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    currency = db.Column(db.String(3), nullable=False, default="INR")
    payment_method = db.Column(db.String(40))
    payment_status = db.Column(db.String(20), nullable=False, default="pending", index=True)
    gateway_reference = db.Column(db.String(255))
    payment_date = db.Column(db.DateTime(timezone=True))
    refund_reference = db.Column(db.String(120))
    refunded_at = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    registration = db.relationship("Registration", backref=db.backref("payment", uselist=False))

    def to_dict(self):
        return {
            "id": self.id,
            "registration_id": self.registration_id,
            "transaction_id": self.transaction_id,
            "gateway_order_id": self.gateway_order_id,
            "amount": float(self.amount),
            "currency": self.currency,
            "payment_method": self.payment_method,
            "payment_status": self.payment_status,
            "payment_date": utc_iso(self.payment_date) if self.payment_date else None,
        }


class Ticket(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    registration_id = db.Column(db.Integer, db.ForeignKey("registration.id", ondelete="CASCADE"), unique=True, nullable=False)
    ticket_number = db.Column(db.String(36), unique=True, nullable=False)
    qr_token = db.Column(db.String(64), unique=True, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="valid")
    generated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    registration = db.relationship("Registration", backref=db.backref("ticket", uselist=False))

    def to_dict(self, include_token=True):
        result = {
            "id": self.id,
            "ticket_number": self.ticket_number,
            "status": self.status,
            "generated_at": utc_iso(self.generated_at),
        }
        if include_token:
            result["qr_token"] = self.qr_token
        return result


class Attendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey("ticket.id", ondelete="CASCADE"), unique=True, nullable=False)
    checked_by = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"))
    check_in_time = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    ticket = db.relationship("Ticket", backref=db.backref("attendance", uselist=False))


class Feedback(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    event_id = db.Column(db.Integer, db.ForeignKey("event.id", ondelete="CASCADE"), nullable=False)
    rating = db.Column(db.Integer, nullable=False)
    comments = db.Column(db.Text)
    suggestions = db.Column(db.Text)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    __table_args__ = (
        db.UniqueConstraint("user_id", "event_id", name="uq_feedback_user_event"),
        db.CheckConstraint("rating >= 1 AND rating <= 5", name="ck_feedback_rating"),
    )
    user = db.relationship("User")


class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)
    title = db.Column(db.String(160), nullable=False)
    message = db.Column(db.Text, nullable=False)
    notification_type = db.Column(db.String(32), nullable=False, default="general")
    is_read = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "message": self.message,
            "notification_type": self.notification_type,
            "is_read": self.is_read,
            "created_at": utc_iso(self.created_at),
        }


class Announcement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey("event.id", ondelete="CASCADE"), nullable=False, index=True)
    organizer_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    title = db.Column(db.String(160), nullable=False)
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)


class ActivityLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    actor_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"), index=True)
    actor_role = db.Column(db.String(20), nullable=False)
    action = db.Column(db.String(80), nullable=False, index=True)
    description = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, index=True)


class RevokedToken(db.Model):
    jti = db.Column(db.String(36), primary_key=True)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False)
