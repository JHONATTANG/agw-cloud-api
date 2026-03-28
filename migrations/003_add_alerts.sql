-- ============================================================
-- Migration 003 — Add Alerts table extensions and audit log
-- ============================================================

-- Alert acknowledgement tracking
ALTER TABLE alerts
    ADD COLUMN IF NOT EXISTS acknowledged_by UUID REFERENCES users(id),
    ADD COLUMN IF NOT EXISTS acknowledged_at TIMESTAMPTZ;

-- Simple audit log table for command actions
CREATE TABLE IF NOT EXISTS command_audit_log (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    command_id  UUID NOT NULL REFERENCES commands(id) ON DELETE CASCADE,
    changed_by  VARCHAR(64) NOT NULL,   -- 'user:<uuid>' or 'edge_gateway'
    old_status  command_status,
    new_status  command_status NOT NULL,
    note        TEXT,
    changed_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX ix_audit_command ON command_audit_log(command_id, changed_at DESC);

-- Function + trigger to auto-populate audit log on status change
CREATE OR REPLACE FUNCTION fn_log_command_status_change()
RETURNS TRIGGER AS $$
BEGIN
    IF OLD.status IS DISTINCT FROM NEW.status THEN
        INSERT INTO command_audit_log (command_id, changed_by, old_status, new_status)
        VALUES (NEW.id, 'edge_gateway', OLD.status, NEW.status);
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_command_status ON commands;
CREATE TRIGGER trg_command_status
    AFTER UPDATE ON commands
    FOR EACH ROW EXECUTE FUNCTION fn_log_command_status_change();
