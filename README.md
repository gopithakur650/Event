# Gatherly — Event Management Platform

Gatherly is a full-stack event platform with public event discovery, participant registration and tickets, organizer tools, and an administrator console. The frontend is React/Vite; the API is Flask with SQLAlchemy and JWT authentication.

## Features

- Search and filter public events by category, date, location, type, and price.
- Participant and organizer registration, with administrator approval for organizers and event submissions.
- Free registrations and Razorpay paid checkout with server-side signature verification and webhook support.
- QR tickets, PDF ticket downloads, organizer attendance scanning, feedback, and notifications.
- Organizer event management, announcements, participant exports, and analytics.
- Admin dashboards, moderation, account/category management, CSV/PDF reports, and activity history.
- Password recovery, profile/file uploads, email notifications, and a scheduled reminder command.

## Requirements

- Python 3.10+
- Node.js 20+
- MySQL 8+ for a shared/production database. SQLite is the local default.

## Run locally

1. Copy `backend/.env.example` to `backend/.env`. The example enables Flask development mode and SQLite works without additional database setup. For MySQL, set `DATABASE_URL` to your SQLAlchemy MySQL URL and create the database first. Set unique `SECRET_KEY` and `JWT_SECRET_KEY` values.
2. Set up and start the API:

   ```powershell
   cd backend
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   python -m flask --app run db upgrade
   py seed.py
   py run.py
   ```

   The migration command creates or upgrades the schema. `database/schema.sql` is a MySQL schema export for manual provisioning.
3. In another terminal, copy `frontend/.env.example` to `frontend/.env`, then run:

   ```powershell
   cd frontend
   npm.cmd install
   npm.cmd run dev
   ```

Open the Vite URL (normally `http://localhost:5173`). The API health check is at `http://localhost:5000/api/health`.

## Initial accounts and demo data

- To create the first administrator, set both `SEED_ADMIN_EMAIL` and `SEED_ADMIN_PASSWORD` in the environment before running `seed.py`. The password must be at least 16 characters.
- Demo data is optional and is restricted to `FLASK_DEBUG=1`. Set `SEED_DEMO_DATA=1` and a unique `SEED_DEMO_PASSWORD` of at least 12 characters before running `seed.py`. The seeded organizer accounts are `asha.organizer@example.test`, `dev.organizer@example.test`, and `meera.organizer@example.test`; participant accounts run from `participant01@example.test` to `participant10@example.test`. All demo accounts use `SEED_DEMO_PASSWORD`.
- Use only development credentials in local environments; do not reuse demo passwords in production.

## Configuration and integrations

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | SQLAlchemy database URL; defaults to local SQLite |
| `SECRET_KEY`, `JWT_SECRET_KEY` | Separate high-entropy application and JWT secrets |
| `FLASK_DEBUG` | Enables development behavior; keep disabled in production |
| `FRONTEND_ORIGIN` | Comma-separated allowed frontend origins for credentialed CORS |
| `JWT_COOKIE_SECURE` | Set to `1` when serving over HTTPS; development mode defaults to `0` |
| `MAIL_SERVER`, `MAIL_PORT`, `MAIL_USE_TLS`, `MAIL_USE_SSL`, `MAIL_USERNAME`, `MAIL_PASSWORD`, `MAIL_DEFAULT_SENDER` | Optional SMTP delivery for account, event, and reminder messages |
| `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET` | Razorpay order creation and payment verification |
| `RAZORPAY_WEBHOOK_SECRET` | Validates Razorpay webhook requests |
| `UPLOAD_FOLDER` | Upload storage directory; defaults to `backend/uploads` |
| `RATELIMIT_STORAGE_URI` | Flask-Limiter storage; defaults to in-memory development storage |
| `CONTACT_EMAIL` | Optional destination for contact-form messages |

Authentication uses an HTTP-only JWT cookie and a CSRF cookie/header for browser requests. Credentialed requests are enabled for the configured frontend origin. API clients may also send JWTs in the `Authorization: Bearer <token>` header.

Paid checkout requires valid Razorpay credentials and the Razorpay Checkout script. The payment webhook endpoint is `POST /api/payments/webhook`; configure the corresponding URL and webhook secret in Razorpay. A captured payment for an expired reservation follows the refund-request path. Event cancellation does not automatically refund already-confirmed paid registrations; handle those refunds with the payment provider.

## Database migrations

Create a new migration after changing models:

```powershell
cd backend
python -m flask --app run db migrate -m "Describe the schema change"
python -m flask --app run db upgrade
```

Review generated migrations before applying them to production. Existing databases should be upgraded with `db upgrade`, not recreated. If a database was previously created with `db.create_all()` and has no Alembic version table, back it up and verify it matches the initial migration before running `python -m flask --app run db stamp head`; do not stamp a database with missing or different columns.

## Event reminders

`backend/send_reminders.py` sends notifications and email for events starting within the next 25 hours, then marks those events as reminded. Schedule it to run periodically using Windows Task Scheduler, cron, or another scheduler. SMTP is optional; in-app notifications are still recorded.

## Documentation

See [API.md](API.md) for endpoint groups, access requirements, and payment, upload, and scheduling notes.

## Deployment notes

Use HTTPS, unique production secrets, a production WSGI server, persistent rate-limit storage, and a managed database. Restrict CORS to trusted origins. Configure SMTP and payment-provider secrets outside source control. Camera-based scanning requires a supported browser and camera permission; no external payment, SMTP, camera, or live MySQL service is included in local automated tests.
