import hashlib
import hmac
from datetime import datetime, timedelta, timezone

from app.payment_gateway import RazorpayGateway
from app.models import Event, Notification, Payment, Registration, User
from extensions import db
from flask_jwt_extended import create_access_token


def create_account(app, email, role, approval_status="approved"):
    with app.app_context():
        user = User(
            full_name=email.split("@")[0],
            email=email,
            role=role,
            approval_status=approval_status,
        )
        user.set_password("safe-password-123")
        db.session.add(user)
        db.session.commit()
        return user.id


def token_for(client, email):
    response = client.post("/api/auth/login", json={
        "email": email,
        "password": "safe-password-123",
    })
    assert response.status_code == 200
    assert "access_token" not in response.json
    with client.application.app_context():
        user = User.query.filter_by(email=email).first()
        return create_access_token(
            identity=str(user.id),
            additional_claims={"auth_version": user.auth_version},
        )


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def create_event(app, organizer_id, *, capacity=1, future=True, fee=0):
    with app.app_context():
        start = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=2 if future else -2)
        event = Event(
            organizer_id=organizer_id,
            category_id=1,
            title="Community Workshop",
            description="A useful test event",
            start_at=start,
            end_at=start + timedelta(hours=2),
            registration_deadline=start - timedelta(days=1),
            capacity=capacity,
            fee=fee,
        )
        db.session.add(event)
        db.session.commit()
        return event.id


def test_registration_roles_event_approval_and_ticket_checkin(app, client):
    organizer_id = create_account(app, "organizer@example.com", "organizer")
    admin_id = create_account(app, "admin@example.com", "admin")
    participant_id = create_account(app, "participant@example.com", "user")
    organizer_token = token_for(client, "organizer@example.com")
    admin_token = token_for(client, "admin@example.com")
    participant_token = token_for(client, "participant@example.com")

    pending_event = create_event(app, organizer_id)
    assert client.get("/api/events").json["total"] == 0
    approved = client.put(
        f"/api/admin/events/{pending_event}/approve",
        headers=auth(admin_token),
    )
    assert approved.status_code == 200
    assert client.get("/api/events").json["total"] == 1

    registration = client.post(
        "/api/registrations",
        json={"event_id": pending_event},
        headers=auth(participant_token),
    )
    assert registration.status_code == 201
    assert registration.json["registration"]["payment_status"] == "not_required"
    duplicate = client.post(
        "/api/registrations",
        json={"event_id": pending_event},
        headers=auth(participant_token),
    )
    assert duplicate.status_code == 409

    ticket = client.get(
        f"/api/tickets/{registration.json['registration']['id']}",
        headers=auth(participant_token),
    )
    assert ticket.status_code == 200
    ticket_data = ticket.json["ticket"]
    checked_in = client.post(
        "/api/attendance/verify",
        json={"qr_token": ticket_data["qr_token"], "event_id": pending_event},
        headers=auth(organizer_token),
    )
    assert checked_in.status_code == 200
    duplicate_checkin = client.post(
        "/api/attendance/verify",
        json={"qr_token": ticket_data["qr_token"], "event_id": pending_event},
        headers=auth(organizer_token),
    )
    assert duplicate_checkin.status_code == 409

    assert client.get(
        "/api/admin/dashboard", headers=auth(participant_token)
    ).status_code == 403
    assert organizer_id and admin_id and participant_id


def test_capacity_and_paid_event_are_enforced(app, client):
    organizer_id = create_account(app, "host@example.com", "organizer")
    first_id = create_account(app, "first@example.com", "user")
    second_id = create_account(app, "second@example.com", "user")
    first_token = token_for(client, "first@example.com")
    second_token = token_for(client, "second@example.com")
    event_id = create_event(app, organizer_id, capacity=1)
    admin_id = create_account(app, "reviewer@example.com", "admin")
    admin_token = token_for(client, "reviewer@example.com")
    assert client.put(
        f"/api/admin/events/{event_id}/approve", headers=auth(admin_token)
    ).status_code == 200

    assert client.post(
        "/api/registrations", json={"event_id": event_id}, headers=auth(first_token)
    ).status_code == 201
    full = client.post(
        "/api/registrations", json={"event_id": event_id}, headers=auth(second_token)
    )
    assert full.status_code == 409
    assert full.json["error"] == "Event is full"

    paid_event_id = create_event(app, organizer_id, capacity=2, fee=25)
    client.put(
        f"/api/admin/events/{paid_event_id}/approve", headers=auth(admin_token)
    )
    unavailable = client.post(
        "/api/registrations",
        json={"event_id": paid_event_id},
        headers=auth(second_token),
    )
    assert unavailable.status_code == 503
    assert first_id != second_id


def test_organizer_onboarding_requires_admin_approval(app, client):
    registration = client.post("/api/auth/register", json={
        "full_name": "New Host",
        "email": "host@example.com",
        "phone": "555-0100",
        "password": "safe-password-123",
        "role": "organizer",
        "organization_name": "Community Studio",
    })
    assert registration.status_code == 201
    organizer_id = registration.json["user"]["id"]
    organizer_token = token_for(client, "host@example.com")
    start = datetime.now(timezone.utc) + timedelta(days=4)
    event_data = {
        "title": "Studio Meetup",
        "description": "A meetup for local makers",
        "category_id": 1,
        "start_at": start.isoformat(),
        "end_at": (start + timedelta(hours=2)).isoformat(),
        "registration_deadline": (start - timedelta(days=1)).isoformat(),
        "capacity": 20,
        "fee": 0,
    }
    assert client.post(
        "/api/events", json=event_data, headers=auth(organizer_token)
    ).status_code == 403

    create_account(app, "admin-host@example.com", "admin")
    admin_token = token_for(client, "admin-host@example.com")
    assert client.put(
        f"/api/admin/organizers/{organizer_id}/approve",
        headers=auth(admin_token),
    ).status_code == 200
    created = client.post(
        "/api/events", json=event_data, headers=auth(organizer_token)
    )
    assert created.status_code == 201
    assert created.json["event"]["approval_status"] == "pending"
    assert client.get("/api/events").json["total"] == 0

    duplicate = client.post("/api/auth/register", json={
        "full_name": "Duplicate Host",
        "email": "HOST@example.com",
        "phone": "555-0101",
        "password": "safe-password-123",
        "role": "organizer",
        "organization_name": "Another Organization",
    })
    assert duplicate.status_code == 409


def test_paid_registration_requires_gateway_signature_and_issues_ticket(app, client, monkeypatch):
    organizer_id = create_account(app, "paid-host@example.com", "organizer")
    create_account(app, "paid-participant@example.com", "user")
    create_account(app, "paid-admin@example.com", "admin")
    participant_token = token_for(client, "paid-participant@example.com")
    admin_token = token_for(client, "paid-admin@example.com")
    event_id = create_event(app, organizer_id, capacity=2, fee=25)
    app.config.update(RAZORPAY_KEY_ID="test_key", RAZORPAY_KEY_SECRET="test-secret")

    def fake_request(_method, url, **_kwargs):
        if url.endswith("/orders"):
            payload = {"id": "order_test_123"}
        else:
            payload = {
                "id": "pay_test_123",
                "order_id": "order_test_123",
                "amount": 2500,
                "status": "captured",
                "method": "card",
            }

        class FakeResponse:
            ok = True

            @staticmethod
            def json():
                return payload

        return FakeResponse()

    monkeypatch.setattr("app.payment_gateway.requests.request", fake_request)
    assert client.put(
        f"/api/admin/events/{event_id}/approve", headers=auth(admin_token)
    ).status_code == 200
    order = client.post(
        "/api/registrations",
        json={"event_id": event_id},
        headers=auth(participant_token),
    )
    assert order.status_code == 201
    checkout = order.json["checkout"]
    assert checkout["amount"] == 2500
    signature = hmac.new(
        b"test-secret",
        b"order_test_123|pay_test_123",
        hashlib.sha256,
    ).hexdigest()
    verified = client.post(
        "/api/payments/verify",
        json={
            "razorpay_order_id": "order_test_123",
            "razorpay_payment_id": "pay_test_123",
            "razorpay_signature": signature,
        },
        headers=auth(participant_token),
    )
    assert verified.status_code == 200
    assert verified.json["registration"]["payment_status"] == "paid"
    assert verified.json["registration"]["ticket"]["ticket_number"].startswith("TKT-")


def test_profile_reset_logout_dashboard_and_reports(app, client):
    admin_id = create_account(app, "reports-admin@example.com", "admin")
    organizer_id = create_account(app, "reports-host@example.com", "organizer")
    participant_id = create_account(app, "reports-user@example.com", "user")
    admin_token = token_for(client, "reports-admin@example.com")
    user_token = token_for(client, "reports-user@example.com")
    event_id = create_event(app, organizer_id)
    approved = client.put(
        f"/api/admin/events/{event_id}/approve", headers=auth(admin_token)
    )
    assert approved.status_code == 200

    dashboard = client.get("/api/admin/dashboard", headers=auth(admin_token))
    assert dashboard.status_code == 200
    assert dashboard.json["total_events"] == 1
    report_csv = client.get("/api/admin/reports?type=events", headers=auth(admin_token))
    assert report_csv.status_code == 200
    assert b"Community Workshop" in report_csv.data
    report_pdf = client.get("/api/admin/reports.pdf", headers=auth(admin_token))
    assert report_pdf.status_code == 200
    assert report_pdf.mimetype == "application/pdf"
    assert client.get("/api/admin/categories", headers=auth(admin_token)).status_code == 200

    updated = client.patch(
        "/api/auth/me",
        json={"college_name": "Community College", "department": "Design"},
        headers=auth(user_token),
    )
    assert updated.status_code == 200
    assert updated.json["user"]["college_name"] == "Community College"

    recovery = client.post("/api/auth/forgot-password", json={"email": "reports-user@example.com"})
    assert recovery.status_code == 200
    from flask import current_app
    from itsdangerous import URLSafeTimedSerializer

    with app.app_context():
        token = URLSafeTimedSerializer(current_app.config["SECRET_KEY"]).dumps(
            {"user_id": participant_id}, salt="gatherly-password-reset-v1"
        )
    reset = client.post(
        "/api/auth/reset-password",
        json={"token": token, "password": "a-new-safe-password"},
    )
    assert reset.status_code == 200
    assert client.post("/api/auth/login", json={
        "email": "reports-user@example.com",
        "password": "a-new-safe-password",
    }).status_code == 200

    assert client.post("/api/auth/logout", headers=auth(admin_token)).status_code == 200
    assert client.get("/api/auth/me", headers=auth(admin_token)).status_code == 401
    assert admin_id and organizer_id


def test_cookie_auth_csrf_and_password_change_invalidation(app):
    create_account(app, "cookie-user@example.com", "user")
    client = app.test_client()
    login = client.post("/api/auth/login", json={
        "email": "cookie-user@example.com",
        "password": "safe-password-123",
    })
    assert login.status_code == 200
    assert client.get_cookie("access_token_cookie", path="/api").http_only
    csrf_cookie = client.get_cookie("csrf_access_token")
    assert csrf_cookie and not csrf_cookie.http_only
    assert client.get("/api/auth/me").status_code == 200
    assert client.post("/api/auth/logout").status_code == 401
    logout = client.post(
        "/api/auth/logout",
        headers={"X-CSRF-TOKEN": csrf_cookie.value},
    )
    assert logout.status_code == 200
    assert client.get("/api/auth/me").status_code == 401

    token = token_for(client, "cookie-user@example.com")
    changed = client.put(
        "/api/auth/me/password",
        json={
            "current_password": "safe-password-123",
            "new_password": "another-safe-password-456",
        },
        headers=auth(token),
    )
    assert changed.status_code == 200
    assert client.get("/api/auth/me", headers=auth(token)).status_code == 401


def test_cancelling_event_expires_pending_payment_and_notifies_participant(
    app, client, monkeypatch
):
    organizer_id = create_account(app, "cancel-host@example.com", "organizer")
    create_account(app, "cancel-user@example.com", "user")
    create_account(app, "cancel-admin@example.com", "admin")
    organizer_token = token_for(client, "cancel-host@example.com")
    participant_token = token_for(client, "cancel-user@example.com")
    admin_token = token_for(client, "cancel-admin@example.com")
    event_id = create_event(app, organizer_id, fee=25)
    app.config.update(RAZORPAY_KEY_ID="test_key", RAZORPAY_KEY_SECRET="test-secret")

    def fake_request(_method, url, **_kwargs):
        if url.endswith("/orders"):
            payload = {"id": "order_to_cancel"}
        elif url.endswith("/payments/pay_to_cancel"):
            payload = {
                "id": "pay_to_cancel",
                "order_id": "order_to_cancel",
                "amount": 2500,
                "status": "captured",
                "method": "card",
            }
        elif url.endswith("/payments/pay_to_cancel/refund"):
            payload = {"id": "refund_to_cancel", "status": "processed"}
        else:
            raise AssertionError(f"Unexpected payment request: {url}")

        class FakeResponse:
            ok = True

            @staticmethod
            def json():
                return payload

        return FakeResponse()

    monkeypatch.setattr("app.payment_gateway.requests.request", fake_request)
    assert client.put(
        f"/api/admin/events/{event_id}/approve", headers=auth(admin_token)
    ).status_code == 200
    order = client.post(
        "/api/registrations",
        json={"event_id": event_id},
        headers=auth(participant_token),
    )
    assert order.status_code == 201

    cancelled = client.post(
        f"/api/events/{event_id}/cancel",
        json={"reason": "Venue unavailable"},
        headers=auth(organizer_token),
    )
    assert cancelled.status_code == 200
    with app.app_context():
        registration = Registration.query.filter_by(event_id=event_id).one()
        payment = Payment.query.filter_by(registration_id=registration.id).one()
        notification = Notification.query.filter_by(
            user_id=registration.user_id,
            notification_type="event_cancelled",
        ).one()
        assert registration.status == "cancelled"
        assert registration.payment_status == "expired"
        assert payment.payment_status == "expired"
        assert "Venue unavailable" in notification.message

    signature = hmac.new(
        b"test-secret",
        b"order_to_cancel|pay_to_cancel",
        hashlib.sha256,
    ).hexdigest()
    late_payment = client.post(
        "/api/payments/verify",
        json={
            "razorpay_order_id": "order_to_cancel",
            "razorpay_payment_id": "pay_to_cancel",
            "razorpay_signature": signature,
        },
        headers=auth(participant_token),
    )
    assert late_payment.status_code == 409
    assert "refund was requested" in late_payment.json["error"]
    with app.app_context():
        registration = Registration.query.filter_by(event_id=event_id).one()
        payment = Payment.query.filter_by(registration_id=registration.id).one()
        assert registration.status == "expired"
        assert payment.payment_status == "refunded"
        assert registration.payment_status == "refunded"
        assert registration.ticket is None
