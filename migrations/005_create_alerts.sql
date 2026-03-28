-- ============================================================
-- MIGRATION 005: alerts
-- Alertas generadas por reglas del Edge Gateway o la nube
-- Depende de: 001_create_users.sql, 002_create_devices.sql
-- ============================================================

CREATE TYPE alert_severity AS ENUM ('INFO', 'WARNING', 'CRITICAL');
CREATE TYPE alert_source   AS ENUM ('EDGE_RULES', 'CLOUD_RULES', 'SYSTEM');

CREATE TABLE alerts (
    id          UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    device_id   UUID            NOT NULL REFERENCES iot_devices(id) ON DELETE CASCADE,
    user_id     UUID            NOT NULL REFERENCES users(id),
    alert_type  TEXT            NOT NULL,       -- LOW_MOISTURE, PH_CRITICAL, HIGH_TEMP, etc.
    severity    alert_severity  NOT NULL DEFAULT 'WARNING',
    source      alert_source    NOT NULL DEFAULT 'EDGE_RULES',
    message     TEXT            NOT NULL,
    context     JSONB           NOT NULL DEFAULT '{}',  -- Valores del sensor que activaron la alerta
    rule_id     TEXT,                           -- ID de la regla de negocio que la generó
    is_read     BOOLEAN         NOT NULL DEFAULT FALSE,
    read_at     TIMESTAMPTZ,
    created_at  TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

-- -------------------------------------------------------
-- Comentarios
-- -------------------------------------------------------
COMMENT ON TABLE  alerts            IS 'Alertas IoT generadas por reglas del Edge o la nube';
COMMENT ON COLUMN alerts.alert_type IS 'Tipo semántico de alerta: LOW_MOISTURE, PH_CRITICAL, HIGH_TEMP, OFFLINE_NODE…';
COMMENT ON COLUMN alerts.context    IS 'Snapshot de valores del sensor que activaron la alerta, ej: {"soil_moisture": 12.5, "threshold": 20}';
COMMENT ON COLUMN alerts.rule_id    IS 'ID de la regla de negocio (Edge YAML o Cloud rule engine) que disparó la alerta';
COMMENT ON COLUMN alerts.read_at    IS 'Timestamp en que el operador marcó la alerta como leída';
