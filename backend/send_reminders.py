from datetime import timedelta

from app import create_app
from app.models import Event, Registration, utcnow
from app.services import notify_user, send_email
from extensions import db

app = create_app()

with app.app_context():
    now = utcnow()
    events = Event.query.filter(
        Event.approval_status == "approved",
        Event.event_status == "active",
        Event.reminder_sent.is_(False),
        Event.start_at > now,
        Event.start_at <= now + timedelta(hours=25),
    ).all()
    sent = 0
    for event in events:
        registrations = Registration.query.filter_by(event_id=event.id, status="confirmed").all()
        for registration in registrations:
            message = (
                f"Reminder: {event.title} starts at "
                f"{event.start_at.strftime('%B %d, %Y %H:%M UTC')} "
                f"at {event.venue or 'the online event venue'}."
            )
            notify_user(registration.user_id, f"Coming up: {event.title}", message, "event_reminder")
            send_email(registration.user.email, f"Event reminder: {event.title}", message)
            sent += 1
        event.reminder_sent = True
    db.session.commit()
    print(f"Sent {sent} event reminders.")
