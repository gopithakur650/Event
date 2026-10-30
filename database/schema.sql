CREATE DATABASE IF NOT EXISTS event_planner CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE event_planner;

CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL, 
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Running upgrade  -> 9e7b89c48fc4

CREATE TABLE category (
    id INTEGER NOT NULL AUTO_INCREMENT, 
    name VARCHAR(80) NOT NULL, 
    description VARCHAR(255), 
    active BOOL NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (name)
);

CREATE TABLE revoked_token (
    jti VARCHAR(36) NOT NULL, 
    expires_at DATETIME NOT NULL, 
    PRIMARY KEY (jti)
);

CREATE TABLE user (
    id INTEGER NOT NULL AUTO_INCREMENT, 
    full_name VARCHAR(120) NOT NULL, 
    email VARCHAR(255) NOT NULL, 
    phone VARCHAR(32), 
    password_hash VARCHAR(255) NOT NULL, 
    auth_version INTEGER NOT NULL, 
    `role` VARCHAR(20) NOT NULL, 
    college_name VARCHAR(180), 
    department VARCHAR(120), 
    student_id VARCHAR(80), 
    profile_image VARCHAR(255), 
    organization_name VARCHAR(160), 
    organization_description TEXT, 
    organization_address VARCHAR(255), 
    organization_logo VARCHAR(255), 
    supporting_document VARCHAR(255), 
    account_status VARCHAR(20) NOT NULL, 
    approval_status VARCHAR(20) NOT NULL, 
    rejection_reason VARCHAR(500), 
    created_at DATETIME NOT NULL, 
    updated_at DATETIME NOT NULL, 
    PRIMARY KEY (id)
);

CREATE INDEX ix_user_account_status ON user (account_status);

CREATE INDEX ix_user_approval_status ON user (approval_status);

CREATE UNIQUE INDEX ix_user_email ON user (email);

CREATE INDEX ix_user_role ON user (`role`);

CREATE TABLE activity_log (
    id INTEGER NOT NULL AUTO_INCREMENT, 
    actor_id INTEGER, 
    actor_role VARCHAR(20) NOT NULL, 
    action VARCHAR(80) NOT NULL, 
    description TEXT NOT NULL, 
    created_at DATETIME NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(actor_id) REFERENCES user (id) ON DELETE SET NULL
);

CREATE INDEX ix_activity_log_action ON activity_log (action);

CREATE INDEX ix_activity_log_actor_id ON activity_log (actor_id);

CREATE INDEX ix_activity_log_created_at ON activity_log (created_at);

CREATE TABLE event (
    id INTEGER NOT NULL AUTO_INCREMENT, 
    organizer_id INTEGER NOT NULL, 
    category_id INTEGER NOT NULL, 
    title VARCHAR(180) NOT NULL, 
    description TEXT NOT NULL, 
    poster VARCHAR(255), 
    event_type VARCHAR(20) NOT NULL, 
    start_at DATETIME NOT NULL, 
    end_at DATETIME NOT NULL, 
    registration_start DATETIME NOT NULL, 
    registration_deadline DATETIME NOT NULL, 
    venue VARCHAR(180) NOT NULL, 
    address VARCHAR(255) NOT NULL, 
    city VARCHAR(100), 
    state VARCHAR(100), 
    postal_code VARCHAR(20), 
    online_meeting_link VARCHAR(500), 
    capacity INTEGER NOT NULL, 
    fee NUMERIC(10, 2) NOT NULL, 
    eligibility TEXT, 
    age_restriction VARCHAR(100), 
    department_restriction VARCHAR(255), 
    event_rules TEXT, 
    required_materials TEXT, 
    contact_person VARCHAR(120), 
    contact_email VARCHAR(255), 
    contact_phone VARCHAR(32), 
    website VARCHAR(500), 
    approval_status VARCHAR(20) NOT NULL, 
    event_status VARCHAR(20) NOT NULL, 
    rejection_reason VARCHAR(500), 
    cancellation_reason VARCHAR(500), 
    reminder_sent BOOL NOT NULL, 
    created_at DATETIME NOT NULL, 
    updated_at DATETIME NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(category_id) REFERENCES category (id) ON DELETE RESTRICT, 
    FOREIGN KEY(organizer_id) REFERENCES user (id) ON DELETE RESTRICT
);

CREATE INDEX ix_event_approval_status ON event (approval_status);

CREATE INDEX ix_event_category_id ON event (category_id);

CREATE INDEX ix_event_event_status ON event (event_status);

CREATE INDEX ix_event_organizer_id ON event (organizer_id);

CREATE INDEX ix_event_start_at ON event (start_at);

CREATE INDEX ix_event_title ON event (title);

CREATE TABLE notification (
    id INTEGER NOT NULL AUTO_INCREMENT, 
    user_id INTEGER NOT NULL, 
    title VARCHAR(160) NOT NULL, 
    message TEXT NOT NULL, 
    notification_type VARCHAR(32) NOT NULL, 
    is_read BOOL NOT NULL, 
    created_at DATETIME NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(user_id) REFERENCES user (id) ON DELETE CASCADE
);

CREATE INDEX ix_notification_user_id ON notification (user_id);

CREATE TABLE announcement (
    id INTEGER NOT NULL AUTO_INCREMENT, 
    event_id INTEGER NOT NULL, 
    organizer_id INTEGER NOT NULL, 
    title VARCHAR(160) NOT NULL, 
    message TEXT NOT NULL, 
    created_at DATETIME NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(event_id) REFERENCES event (id) ON DELETE CASCADE, 
    FOREIGN KEY(organizer_id) REFERENCES user (id) ON DELETE CASCADE
);

CREATE INDEX ix_announcement_event_id ON announcement (event_id);

CREATE TABLE feedback (
    id INTEGER NOT NULL AUTO_INCREMENT, 
    user_id INTEGER NOT NULL, 
    event_id INTEGER NOT NULL, 
    rating INTEGER NOT NULL, 
    comments TEXT, 
    suggestions TEXT, 
    created_at DATETIME NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT ck_feedback_rating CHECK (rating >= 1 AND rating <= 5), 
    FOREIGN KEY(event_id) REFERENCES event (id) ON DELETE CASCADE, 
    FOREIGN KEY(user_id) REFERENCES user (id) ON DELETE CASCADE, 
    CONSTRAINT uq_feedback_user_event UNIQUE (user_id, event_id)
);

CREATE TABLE registration (
    id INTEGER NOT NULL AUTO_INCREMENT, 
    user_id INTEGER NOT NULL, 
    event_id INTEGER NOT NULL, 
    registration_number VARCHAR(36) NOT NULL, 
    status VARCHAR(24) NOT NULL, 
    payment_status VARCHAR(20) NOT NULL, 
    pending_expires_at DATETIME, 
    created_at DATETIME NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(event_id) REFERENCES event (id) ON DELETE CASCADE, 
    FOREIGN KEY(user_id) REFERENCES user (id) ON DELETE CASCADE, 
    UNIQUE (registration_number), 
    CONSTRAINT uq_registration_user_event UNIQUE (user_id, event_id)
);

CREATE INDEX ix_registration_event_id ON registration (event_id);

CREATE INDEX ix_registration_status ON registration (status);

CREATE INDEX ix_registration_user_id ON registration (user_id);

CREATE TABLE payment (
    id INTEGER NOT NULL AUTO_INCREMENT, 
    registration_id INTEGER NOT NULL, 
    transaction_id VARCHAR(120), 
    gateway_order_id VARCHAR(120), 
    amount NUMERIC(10, 2) NOT NULL, 
    currency VARCHAR(3) NOT NULL, 
    payment_method VARCHAR(40), 
    payment_status VARCHAR(20) NOT NULL, 
    gateway_reference VARCHAR(255), 
    payment_date DATETIME, 
    refund_reference VARCHAR(120), 
    refunded_at DATETIME, 
    created_at DATETIME NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(registration_id) REFERENCES registration (id) ON DELETE CASCADE, 
    UNIQUE (gateway_order_id), 
    UNIQUE (registration_id), 
    UNIQUE (transaction_id)
);

CREATE INDEX ix_payment_payment_status ON payment (payment_status);

CREATE TABLE ticket (
    id INTEGER NOT NULL AUTO_INCREMENT, 
    registration_id INTEGER NOT NULL, 
    ticket_number VARCHAR(36) NOT NULL, 
    qr_token VARCHAR(64) NOT NULL, 
    status VARCHAR(20) NOT NULL, 
    generated_at DATETIME NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(registration_id) REFERENCES registration (id) ON DELETE CASCADE, 
    UNIQUE (qr_token), 
    UNIQUE (registration_id), 
    UNIQUE (ticket_number)
);

CREATE TABLE attendance (
    id INTEGER NOT NULL AUTO_INCREMENT, 
    ticket_id INTEGER NOT NULL, 
    checked_by INTEGER, 
    check_in_time DATETIME NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(checked_by) REFERENCES user (id) ON DELETE SET NULL, 
    FOREIGN KEY(ticket_id) REFERENCES ticket (id) ON DELETE CASCADE, 
    UNIQUE (ticket_id)
);

INSERT INTO alembic_version (version_num) VALUES ('9e7b89c48fc4');

