-- ============================================================
-- MIGRATION 006: indexes
-- Índices optimizados para queries del dashboard y del Edge
-- Depende de: 003_create_telemetry.sql, 004_create_commands.sql,
--             005_create_alerts.sql, 002_create_devices.sql
-- ============================================================

-- ── Telemetría ─────────────────────────────────────────────
-- Query más común: datos de un dispositivo en rango de fechas
CREATE INDEX CONCURRENTLY idx_telemetry_device_timestamp
    ON telemetry (device_id, timestamp DESC);

-- Última lectura por dispositivo (dashboard principal)
CREATE INDEX CONCURRENTLY idx_telemetry_latest
    ON telemetry (device_id, received_at DESC);

-- ── Comandos ───────────────────────────────────────────────
-- Polling frecuente del Edge Gateway — solo comandos PENDING
CREATE INDEX CONCURRENTLY idx_commands_pending
    ON device_commands (device_type, status, created_at)
    WHERE status = 'PENDING';

-- Historial de comandos por dispositivo
CREATE INDEX CONCURRENTLY idx_commands_device
    ON device_commands (device_id, created_at DESC);

-- ── Alertas ────────────────────────────────────────────────
-- Alertas no leídas por usuario (badge de notificaciones)
CREATE INDEX CONCURRENTLY idx_alerts_unread
    ON alerts (user_id, is_read, created_at DESC)
    WHERE is_read = FALSE;

-- Historial de alertas por dispositivo
CREATE INDEX CONCURRENTLY idx_alerts_device
    ON alerts (device_id, severity, created_at DESC);

-- ── Dispositivos ───────────────────────────────────────────
-- Dispositivos activos por usuario
CREATE INDEX CONCURRENTLY idx_devices_user
    ON iot_devices (user_id, is_active);

-- Lookup rápido por UID de firmware (ya es UNIQUE, índice explícito)
CREATE UNIQUE INDEX IF NOT EXISTS idx_devices_uid
    ON iot_devices (device_uid);

-- GIN sobre JSONB config para queries de configuración
CREATE INDEX CONCURRENTLY idx_devices_config
    ON iot_devices USING GIN (config);
