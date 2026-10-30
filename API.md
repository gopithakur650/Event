# Gatherly API

The API is served under `/api`. JSON errors use an `error` field. Browser requests use credentialed cookies; mutating cookie-authenticated requests must include the CSRF token from `csrf_access_token` in the `X-CSRF-TOKEN` header. Non-browser clients can use `Authorization: Bearer <JWT>`.

Roles used below: **public** means no login is required; **participant**, **organizer**, and **admin** require an active account with that role. Organizers must also be approved to create events.

## Authentication and account

| Method | Path | Access | Purpose |
|---|---|---|---|
| POST | `/auth/register` | Public | Create a participant or pending organizer account |
| POST | `/auth/login` | Public | Sign in; optional JSON `remember_me` |
| POST | `/auth/logout` | Authenticated | Revoke the current JWT and clear auth cookies |
| GET | `/auth/me` | Authenticated | Return the current profile |
| PATCH | `/auth/me` | Authenticated | Update editable profile fields |
| PUT | `/auth/me/password` | Authenticated | Change password; invalidates all existing sessions |
| DELETE | `/auth/me` | Authenticated | Delete the current account |
| POST | `/auth/forgot-password` | Public | Request a password-reset email |
| POST | `/auth/reset-password` | Public | Reset password with the emailed token |
| POST | `/auth/me/profile-image` | Authenticated | Upload a profile image |
| POST | `/auth/me/organization-files` | Organizer | Upload organizer logo or supporting documents |

Public registration does not allow admin accounts. Password-reset responses do not disclose whether an email address exists.

## Events

| Method | Path | Access | Purpose |
|---|---|---|---|
| GET | `/events` | Public | Paginated event discovery; supports `search`, `category`, `date_from`, `date_to`, `event_type`, `price`, `sort`, `page`, and `per_page` |
| GET | `/events/featured`, `/events/upcoming`, `/events/stats`, `/events/categories` | Public | Home-page event lists, platform counts, and active categories |
| GET | `/events/<id>` | Public | Event details |
| POST | `/events/contact` | Public | Submit a contact message |
| POST | `/events` | Organizer | Create a draft or submit an event for review (`save_as=draft|submit`; defaults to `submit`) |
| GET | `/events/mine` | Organizer | List the organizer's events |
| GET | `/events/dashboard`, `/events/analytics` | Organizer | Organizer overview and analytics |
| PUT | `/events/<id>` | Organizer | Edit an event |
| PUT | `/events/<id>/submit` | Organizer | Submit or resubmit an event for admin review |
| POST | `/events/<id>/poster` | Organizer | Upload an event poster |
| DELETE | `/events/<id>` | Organizer | Delete an eligible event |
| POST | `/events/<id>/cancel` | Organizer | Cancel an event with a reason and notify participants |
| GET | `/events/<id>/participants`, `/events/<id>/participants.csv` | Organizer | View or export event registrants |
| GET | `/events/<id>/announcements` | Organizer | List event announcements |
| POST | `/events/<id>/announcements` | Organizer | Send an announcement to registrants |
| GET | `/events/<id>/attendance` | Organizer | View event attendance |

Dates should be ISO-8601 values. Event create/update requests include the category, title, description, start/end times, registration window, capacity, and fee. New events require administrator approval before public registration opens.

## Registrations, payments, tickets, and feedback

| Method | Path | Access | Purpose |
|---|---|---|---|
| POST | `/registrations` | Participant | Register for a free event or create/reuse a 15-minute paid checkout reservation |
| GET | `/registrations/my` | Participant | List own registrations |
| GET | `/registrations/<id>` | Participant | View an owned registration |
| DELETE | `/registrations/<id>` | Participant | Cancel an eligible registration |
| POST | `/payments/verify` | Participant | Verify Razorpay order/payment/signature and issue a ticket |
| POST | `/payments/webhook` | Razorpay | Receive signed payment-provider events |
| GET | `/tickets/<registration_id>` | Participant | Get ticket details and QR token |
| GET | `/tickets/<registration_id>/qr` | Participant | Download ticket QR image |
| GET | `/tickets/<registration_id>/download` | Participant | Download ticket PDF |
| POST | `/attendance/verify` | Organizer | Verify a ticket QR token and check a participant in |
| GET | `/notifications` | Participant | List notifications |
| PUT | `/notifications/<id>/read` | Participant | Mark a notification read |
| POST | `/feedback` | Participant | Submit event feedback |
| GET | `/feedback/<event_id>` | Organizer | View feedback for an event |

Paid checkout requires `RAZORPAY_KEY_ID` and `RAZORPAY_KEY_SECRET`; configure Razorpay's webhook with `RAZORPAY_WEBHOOK_SECRET`. The backend verifies the payment signature and captured amount before confirming registration or issuing a ticket. Expired captured payments enter a refund-request flow. Organizer event cancellation notifies registrants and expires unpaid reservations, but does not automatically refund already-confirmed paid registrations.

## Administration

All routes in this section require **admin** access.

| Method | Path | Purpose |
|---|---|---|
| GET | `/admin/dashboard` | Platform metrics and activity |
| GET | `/admin/events`, `/admin/events/pending` | List or review pending events |
| PUT | `/admin/events/<id>/approve`, `/admin/events/<id>/reject`, `/admin/events/<id>` | Moderate or update events |
| GET | `/admin/users` | List accounts |
| PUT | `/admin/users/<id>`, `/admin/users/<id>/status` | Update account fields or status |
| DELETE | `/admin/users/<id>` | Delete an account |
| GET | `/admin/organizers` | List organizer applications |
| GET | `/admin/organizers/<id>/files/<kind>` | Review an organizer document |
| PUT | `/admin/organizers/<id>/approve`, `/admin/organizers/<id>/reject`, `/admin/organizers/<id>/status` | Review or update an organizer |
| GET | `/admin/registrations` | List registrations |
| PUT | `/admin/registrations/<id>/cancel` | Cancel a registration |
| GET | `/admin/categories` | List categories |
| POST | `/admin/categories` | Create a category |
| PUT | `/admin/categories/<id>` | Update a category |
| DELETE | `/admin/categories/<id>` | Delete an unused category |
| GET | `/admin/reports?type=events\|registrations\|revenue\|attendance\|categories` | Download a CSV report |
| GET | `/admin/reports.pdf` | Download a PDF summary |
| GET | `/admin/activity` | View the activity log |
| GET | `/admin/feedback` | View platform feedback |

## Health and uploaded images

- `GET /health` returns `{"status":"ok"}`.
- `GET /uploads/<path>` serves public images only. Organizer documents are served only through the administrator-authorized document endpoint.

## Operational behavior

- `python -m flask --app run db upgrade` applies database migrations from the `backend` directory.
- `python seed.py` inserts categories and optional development/demo data after migrations have been applied. Demo data requires both `FLASK_DEBUG=1` and `SEED_DEMO_DATA=1`.
- Run `python send_reminders.py` periodically through an external scheduler to send reminders for events beginning within 25 hours. It is not a continuously running worker.
- SMTP is optional. Configure the `MAIL_*` environment variables to deliver email; in-app notifications are stored independently.
