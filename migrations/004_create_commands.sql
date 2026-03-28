-- ============================================================
-- MIGRATION 004: device_commands
-- Cola de comandos de control remoto para nodos IoT
-- Depende de: 001_create_users.sql, 002_create_devices.sql
-- ============================================================

CREATE TYPE command_type AS ENUM (
    'ACTIVATE_PUMP',
    'DEACTIVATE_PUMP',
    'OPEN_VALVE_1',
    'CLOSE_VALVE_1',
    'OPEN_VALVE_2',
    'CLOSE_VALVE_2',
    'SET_CONFIG',
    'RESTART_NODE',
    'REQUEST_STATUS'
);

CREATE TYPE command_status AS ENUM ('PENDING', 'SENT', 'EXECUTED', 'FAILED', 'EXPIRED');

CREATE TABLE device_commands (
    id             UUID           PRIMARY KEY DEFAULT gen_random_uuid(),
    device_id      UUID           NOT NULL REFERENCES iot_devices(id) ON DELETE CASCADE,
    device_type    device_type    NOT NULL,
    command_type   command_type   NOT NULL,
    params         JSONB          NOT NULL DEFAULT '{}',   -- {"duration_seconds": 30}
    status         command_status NOT NULL DEFAULT 'PENDING',
    created_by     UUID           NOT NULL REFERENCES users(id),
    created_at     TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
    sent_at        TIMESTAMPTZ,         -- Cuando el Edge Gateway descargó el comando
    executed_at    TIMESTAMPTZ,         -- Cuando el ESP32 confirmó ejecución (ACK)
    expires_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW() + INTERVAL '10 minutes',
    error_message  TEXT,
    ack_payload    JSONB                -- Respuesta ACK completa del nodo
);

-- -------------------------------------------------------
-- Función: expirar comandos PENDING vencidos
-- Ejecutar periódicamente via pg_cron (ver README)
-- -------------------------------------------------------
CREATE OR REPLACE FUNCTION expire_old_commands()
RETURNS void AS $$
    UPDATE device_commands
    SET status = 'EXPIRED'
    WHERE status = 'PENDING'
      AND expires_at < NOW();
$$ LANGUAGE sql;

-- -------------------------------------------------------
-- Comentarios
-- -------------------------------------------------------
COMMENT ON TABLE  device_commands            IS 'Cola de comandos de control remoto IoT';
COMMENT ON COLUMN device_commands.params      IS 'Parámetros del comando, ej: {"duration_seconds": 30}';
COMMENT ON COLUMN device_commands.sent_at     IS 'Timestamp en que el Edge Gateway descargó el comando via HTTP polling';
COMMENT ON COLUMN device_commands.executed_at IS 'Timestamp del ACK del nodo ESP32 confirmando ejecución';
COMMENT ON COLUMN device_commands.expires_at  IS 'Comandos PENDING más antiguos que este tiempo pasan a EXPIRED automáticamente';
COMMENT ON COLUMN device_commands.ack_payload IS 'JSON de respuesta del ESP32: {"status": "ok", "actuator_state": {...}}';
