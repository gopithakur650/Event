import os
from datetime import timedelta
from decimal import Decimal
from sqlalchemy import inspect

from app import create_app
from app.models import (
    Category,
    Event,
    Feedback,
    Notification,
    Registration,
    User,
    utcnow,
)
from app.services import create_ticket
from extensions import db

app = create_app()
CATEGORIES = (
    "Technical Events",
    "Cultural Events",
    "Workshops",
    "Seminars",
    "Sports Events",
    "Music and Entertainment",
    "Conferences",
    "Competitions",
    "Other Events",
)

ORGANIZERS = (
    ("Asha Rao", "Bengaluru Makers Collective", "asha.organizer@example.test"),
    ("Dev Shah", "Open Source Bengaluru", "dev.organizer@example.test"),
    ("Meera Iyer", "The Good Gathering Co.", "meera.organizer@example.test"),
)

PARTICIPANTS = (
    "Nisha Kumar", "Rahul Menon", "Ishita Rao", "Kabir Shah", "Ananya Das",
    "Rohan Iyer", "Priya Nair", "Arjun Patel", "Sana Khan", "Vikram Joshi",
)

EVENTS = (
    ("Build for Good: AI and Community", "Technical Events", 8, 0, "offline"),
    ("Indie Sounds Under the Stars", "Music and Entertainment", 12, 299, "offline"),
    ("Clay, Coffee and Conversation", "Workshops", 5, 499, "offline"),
    ("Open Source Spring Challenge", "Competitions", 18, 99, "hybrid"),
    ("Sunday Futsal Social", "Sports Events", 10, 0, "offline"),
    ("Stories of the City: Culture Night", "Cultural Events", 15, 199, "offline"),
    ("Future of Work Community Forum", "Conferences", 24, 799, "hybrid"),
    ("Climate Solutions Student Seminar", "Seminars", 30, 0, "online"),
    ("Campus Hack Day", "Technical Events", -30, 0, "offline"),
    ("Folk Dance and Food Festival", "Cultural Events", -45, 0, "offline"),
)


def get_or_create_user(email, name, password, role, **fields):
    user = User.query.filter_by(email=email).first()
    if user:
        return user
    user = User(full_name=name, email=email, role=role, **fields)
    user.set_password(password)
    db.session.add(user)
    db.session.flush()
    return user


with app.app_context():
    if not inspect(db.engine).has_table("alembic_version"):
        raise SystemExit(
            "Database migrations are not applied. Run `python -m flask db upgrade` first."
        )
    for name in CATEGORIES:
        if not Category.query.filter_by(name=name).first():
            db.session.add(Category(name=name))
    db.session.commit()

    admin_email = os.getenv("SEED_ADMIN_EMAIL", "").strip().lower()
    admin_password = os.getenv("SEED_ADMIN_PASSWORD", "")
    if bool(admin_email) != bool(admin_password):
        raise SystemExit("Set both SEED_ADMIN_EMAIL and SEED_ADMIN_PASSWORD to seed an admin.")
    if admin_password and len(admin_password) < 16:
        raise SystemExit("SEED_ADMIN_PASSWORD must be at least 16 characters.")
    if admin_email and not User.query.filter_by(email=admin_email).first():
        get_or_create_user(admin_email, "System Administrator", admin_password, "admin")
        db.session.commit()

    demo = os.getenv("SEED_DEMO_DATA") == "1"
    demo_password = os.getenv("SEED_DEMO_PASSWORD", "")
    if not demo:
        print("Categories are ready. Set SEED_DEMO_DATA=1 and a unique SEED_DEMO_PASSWORD to add development demo data.")
        raise SystemExit(0)
    if not app.config["DEBUG"]:
        raise SystemExit("Demo data may only be seeded when FLASK_DEBUG=1.")
    if len(demo_password) < 12:
        raise SystemExit("Set SEED_DEMO_PASSWORD to a unique password of at least 12 characters.")

    organizers = []
    for name, organization, email in ORGANIZERS:
        organizer = get_or_create_user(
            email,
            name,
            demo_password,
            "organizer",
            organization_name=organization,
            organization_description=f"{organization} brings local communities together.",
            organization_address="Bengaluru, Karnataka",
            phone="+91-90000-00001",
            approval_status="approved",
        )
        organizers.append(organizer)
    participants = []
    for index, name in enumerate(PARTICIPANTS, start=1):
        participants.append(get_or_create_user(
            f"participant{index:02d}@example.test",
            name,
            demo_password,
            "user",
            phone=f"+91-90000-{index:05d}",
            college_name="Bengaluru Community University",
            department="Community Studies",
        ))

    categories = {category.name: category for category in Category.query.all()}
    now = utcnow()
    events = []
    for index, (title, category_name, days, fee, event_type) in enumerate(EVENTS):
        event = Event.query.filter_by(title=title).first()
        if not event:
            start = now + timedelta(days=days)
            end = start + timedelta(hours=4)
            event = Event(
                organizer_id=organizers[index % len(organizers)].id,
                category_id=categories[category_name].id,
                title=title,
                description=f"Join the community for {title.lower()}. Meet new people, learn together, and take part in an experience planned by local organizers.",
                event_type=event_type,
                start_at=start,
                end_at=end,
                registration_start=now - timedelta(days=2),
                registration_deadline=start - timedelta(days=1),
                venue="Bengaluru Community Hall" if event_type != "online" else "",
                address="12 Community Road, Bengaluru" if event_type != "online" else "",
                city="Bengaluru",
                state="Karnataka",
                postal_code="560001",
                online_meeting_link="https://example.test/events/community" if event_type == "online" else None,
                capacity=120,
                fee=Decimal(str(fee)),
                eligibility="Open to all community members",
                event_rules="Please arrive 15 minutes before the event.",
                contact_person=organizers[index % len(organizers)].full_name,
                contact_email=organizers[index % len(organizers)].email,
                approval_status="approved",
                event_status="active",
            )
            db.session.add(event)
            db.session.flush()
        events.append(event)

    db.session.commit()
    free_events = [event for event in events if event.fee == 0]
    for index, participant in enumerate(participants):
        event = free_events[index % len(free_events)]
        registration = Registration.query.filter_by(
            user_id=participant.id, event_id=event.id
        ).first()
        if not registration:
            registration = Registration(
                user_id=participant.id,
                event_id=event.id,
                registration_number=f"DEMO-{participant.id:04d}-{event.id:04d}",
                status="confirmed",
                payment_status="not_required",
            )
            db.session.add(registration)
            db.session.flush()
            create_ticket(registration)
            db.session.add(Notification(
                user_id=participant.id,
                title="Demo registration confirmed",
                message=f"Your registration for {event.title} is confirmed.",
                notification_type="registration_confirmation",
            ))
        completed = event.end_at < now
        if completed and not Feedback.query.filter_by(user_id=participant.id, event_id=event.id).first():
            db.session.add(Feedback(
                user_id=participant.id,
                event_id=event.id,
                rating=5,
                comments="A welcoming and well-organized community event.",
                suggestions="Keep hosting gatherings like this.",
            ))
    db.session.commit()
    print("Development demo data is ready.")
    print("Admin: set SEED_ADMIN_EMAIL and SEED_ADMIN_PASSWORD before running the seeder.")
    print("Organizers: asha.organizer@example.test, dev.organizer@example.test, meera.organizer@example.test")
    print("Participants: participant01@example.test through participant10@example.test")
    print("All demo accounts use the password supplied in SEED_DEMO_PASSWORD.")
