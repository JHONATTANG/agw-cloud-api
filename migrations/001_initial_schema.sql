-- ============================================================
-- Migration 001 — Initial schema
-- VitalCrop AGW Cloud API
-- ============================================================

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ── Users ────────────────────────────────────────────────────
CREATE TYPE user_role AS ENUM ('ADMIN', 'OPERATOR', 'VIEWER');

CREATE TABLE IF NOT EXISTS users (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email             VARCHAR(255) UNIQUE NOT NULL,
    hashed_password   VARCHAR(255) NOT NULL,
    full_name         VARCHAR(255),
    role              user_role NOT NULL DEFAULT 'OPERATOR',
    is_active         BOOLEAN NOT NULL DEFAULT TRUE,
    refresh_token     VARCHAR(512),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX ix_users_email ON users(email);

-- ── Devices ──────────────────────────────────────────────────
CREATE TYPE device_type   AS ENUM ('SOIL', 'HYDRO');
CREATE TYPE device_status AS ENUM ('ONLINE', 'OFFLINE', 'ERROR');

CREATE TABLE IF NOT EXISTS devices (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    device_uid        VARCHAR(64) UNIQUE NOT NULL,
    name              VARCHAR(255) NOT NULL,
    device_type       device_type NOT NULL,
    status            device_status NOT NULL DEFAULT 'OFFLINE',
    owner_id          UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    location          VARCHAR(255),
    firmware_version  VARCHAR(32),
    metadata          JSONB,
    last_seen_at      TIMESTAMPTZ,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX ix_devices_owner   ON devices(owner_id);
CREATE INDEX ix_devices_uid     ON devices(device_uid);

-- ── Telemetry ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS telemetry (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    device_id    UUID NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    device_uid   VARCHAR(64) NOT NULL,
    sensor_type  VARCHAR(64) NOT NULL,
    value        DOUBLE PRECISION NOT NULL,
    unit         VARCHAR(32),
    raw          JSONB,
    recorded_at  TIMESTAMPTZ NOT NULL,
    ingested_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX ix_telemetry_device_recorded ON telemetry(device_id, recorded_at DESC);

-- ── Commands ─────────────────────────────────────────────────
CREATE TYPE command_type   AS ENUM ('ACTIVATE_PUMP','OPEN_VALVE','CLOSE_VALVE','SET_CONFIG');
CREATE TYPE command_status AS ENUM ('PENDING','SENT','EXECUTED','FAILED');

CREATE TABLE IF NOT EXISTS commands (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    device_id      UUID NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    device_uid     VARCHAR(64) NOT NULL,
    device_type    VARCHAR(16) NOT NULL,
    command_type   command_type NOT NULL,
    params         JSONB,
    status         command_status NOT NULL DEFAULT 'PENDING',
    created_by     UUID NOT NULL REFERENCES users(id),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    executed_at    TIMESTAMPTZ,
    error_message  VARCHAR(512)
);

CREATE INDEX ix_commands_status ON commands(status);
CREATE INDEX ix_commands_device ON commands(device_id);

-- ── Alerts ───────────────────────────────────────────────────
CREATE TYPE alert_severity AS ENUM ('INFO','WARNING','CRITICAL');

CREATE TABLE IF NOT EXISTS alerts (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    device_id        UUID NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    device_uid       VARCHAR(64) NOT NULL,
    sensor_type      VARCHAR(64),
    severity         alert_severity NOT NULL DEFAULT 'WARNING',
    title            VARCHAR(255) NOT NULL,
    message          TEXT,
    threshold_value  DOUBLE PRECISION,
    actual_value     DOUBLE PRECISION,
    is_read          BOOLEAN NOT NULL DEFAULT FALSE,
    triggered_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    read_at          TIMESTAMPTZ
);

CREATE INDEX ix_alerts_device   ON alerts(device_uid);
CREATE INDEX ix_alerts_is_read  ON alerts(is_read);
