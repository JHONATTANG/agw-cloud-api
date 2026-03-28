-- ============================================================
-- MIGRATION 003: telemetry
-- Lecturas de sensores — tabla de alta frecuencia
-- Particionada por RANGE(timestamp) — una partición por año
-- Depende de: 002_create_devices.sql
-- ============================================================

CREATE TABLE telemetry (
    id               UUID        NOT NULL DEFAULT gen_random_uuid(),
    device_id        UUID        NOT NULL REFERENCES iot_devices(id) ON DELETE CASCADE,
    timestamp        TIMESTAMPTZ NOT NULL,         -- Timestamp del dispositivo (UTC)
    received_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),  -- Timestamp de ingesta

    -- ── Sensores SOIL ──────────────────────────────────────
    temperature      NUMERIC(6,2),    -- °C    (suelo / ambiente)
    humidity         NUMERIC(5,2),    -- %     (humedad relativa)
    soil_moisture    NUMERIC(5,2),    -- %     (0–100, capacitivo)

    -- ── Sensores HYDRO ─────────────────────────────────────
    ph               NUMERIC(5,2),    -- 0–14
    ec               NUMERIC(7,3),    -- mS/cm  (conductividad eléctrica)
    water_temp       NUMERIC(6,2),    -- °C    (temperatura solución)
    water_level      NUMERIC(5,2),    -- %     (0–100)

    -- ── Estado de actuadores en el momento de la lectura ───
    pump_active      BOOLEAN  DEFAULT FALSE,
    valve_1_open     BOOLEAN  DEFAULT FALSE,
    valve_2_open     BOOLEAN  DEFAULT FALSE,

    -- ── Metadatos del nodo ─────────────────────────────────
    rssi             SMALLINT,        -- dBm   (señal WiFi)
    firmware_version TEXT,
    raw_payload      JSONB,           -- Payload JSON completo del ESP32 (auditoría)

    PRIMARY KEY (id, timestamp)
) PARTITION BY RANGE (timestamp);

-- -------------------------------------------------------
-- Particiones anuales
-- Añadir una nueva partición cada año antes de que comience
-- -------------------------------------------------------
CREATE TABLE telemetry_2024 PARTITION OF telemetry
    FOR VALUES FROM ('2024-01-01 00:00:00+00') TO ('2025-01-01 00:00:00+00');

CREATE TABLE telemetry_2025 PARTITION OF telemetry
    FOR VALUES FROM ('2025-01-01 00:00:00+00') TO ('2026-01-01 00:00:00+00');

CREATE TABLE telemetry_2026 PARTITION OF telemetry
    FOR VALUES FROM ('2026-01-01 00:00:00+00') TO ('2027-01-01 00:00:00+00');

CREATE TABLE telemetry_2027 PARTITION OF telemetry
    FOR VALUES FROM ('2027-01-01 00:00:00+00') TO ('2028-01-01 00:00:00+00');

-- -------------------------------------------------------
-- Comentarios
-- -------------------------------------------------------
COMMENT ON TABLE  telemetry                 IS 'Telemetría de alta frecuencia de nodos IoT. Particionada por año.';
COMMENT ON COLUMN telemetry.timestamp       IS 'Timestamp Unix del momento de lectura en el dispositivo (UTC)';
COMMENT ON COLUMN telemetry.received_at     IS 'Momento exacto en que la API Cloud recibió y persistió el registro';
COMMENT ON COLUMN telemetry.raw_payload     IS 'JSON original del ESP32 para trazabilidad completa';
COMMENT ON COLUMN telemetry.ec              IS 'Electrical Conductivity en mS/cm — indicador de nutrientes en solución';
COMMENT ON COLUMN telemetry.rssi            IS 'Received Signal Strength Indicator en dBm (negativo, mayor = mejor señal)';
