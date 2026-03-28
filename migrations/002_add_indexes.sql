-- ============================================================
-- Migration 002 — Performance Indexes
-- ============================================================

-- Compound index for telemetry sensor type filtering
CREATE INDEX IF NOT EXISTS ix_telemetry_device_sensor
    ON telemetry(device_id, sensor_type, recorded_at DESC);

-- Index for alerts unread by device
CREATE INDEX IF NOT EXISTS ix_alerts_device_unread
    ON alerts(device_uid, is_read)
    WHERE is_read = FALSE;

-- Index for command history ordered lookup by device
CREATE INDEX IF NOT EXISTS ix_commands_device_created
    ON commands(device_id, created_at DESC);

-- Partial index for PENDING commands only (used by edge polling)
CREATE INDEX IF NOT EXISTS ix_commands_pending
    ON commands(created_at ASC)
    WHERE status = 'PENDING';

-- GIN index for JSONB metadata search
CREATE INDEX IF NOT EXISTS ix_devices_metadata
    ON devices USING GIN(metadata jsonb_path_ops);
