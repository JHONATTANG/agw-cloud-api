-- ============================================================
-- MIGRATION 007: views
-- Vistas optimizadas para el dashboard de VitalCrop
-- Depende de: 003_create_telemetry.sql, 002_create_devices.sql
-- ============================================================

-- ── Vista: última telemetría de cada dispositivo ───────────
-- Ideal para el widget de estado en el dashboard principal
CREATE OR REPLACE VIEW device_last_telemetry AS
SELECT DISTINCT ON (t.device_id)
    t.device_id,
    d.device_uid,
    d.device_type,
    d.location,
    d.gateway_id,
    d.status         AS device_status,
    d.firmware_version,

    t.timestamp,
    t.received_at,

    -- SOIL
    t.temperature,
    t.humidity,
    t.soil_moisture,

    -- HYDRO
    t.ph,
    t.ec,
    t.water_temp,
    t.water_level,

    -- Actuadores
    t.pump_active,
    t.valve_1_open,
    t.valve_2_open,

    -- Calidad de señal
    t.rssi
FROM telemetry t
JOIN iot_devices d ON d.id = t.device_id
ORDER BY t.device_id, t.timestamp DESC;

COMMENT ON VIEW device_last_telemetry IS
    'Última lectura de cada dispositivo — ideal para el dashboard principal';


-- ── Vista: resumen diario por dispositivo ──────────────────
-- Usado por los gráficos de tendencia histórica (7 / 30 días)
CREATE OR REPLACE VIEW telemetry_daily_summary AS
SELECT
    device_id,
    DATE(timestamp)                       AS day,

    -- Temperatura
    AVG(temperature)::NUMERIC(6,2)        AS avg_temp,
    MIN(temperature)::NUMERIC(6,2)        AS min_temp,
    MAX(temperature)::NUMERIC(6,2)        AS max_temp,

    -- Humedad
    AVG(humidity)::NUMERIC(5,2)           AS avg_humidity,
    MIN(humidity)::NUMERIC(5,2)           AS min_humidity,
    MAX(humidity)::NUMERIC(5,2)           AS max_humidity,

    -- Suelo
    AVG(soil_moisture)::NUMERIC(5,2)      AS avg_soil_moisture,

    -- Hidro
    AVG(ph)::NUMERIC(5,2)                 AS avg_ph,
    MIN(ph)::NUMERIC(5,2)                 AS min_ph,
    MAX(ph)::NUMERIC(5,2)                 AS max_ph,
    AVG(ec)::NUMERIC(7,3)                 AS avg_ec,
    AVG(water_temp)::NUMERIC(6,2)         AS avg_water_temp,
    AVG(water_level)::NUMERIC(5,2)        AS avg_water_level,

    COUNT(*)                              AS record_count
FROM telemetry
GROUP BY device_id, DATE(timestamp);

COMMENT ON VIEW telemetry_daily_summary IS
    'Agregados diarios por dispositivo — optimizado para gráficas de tendencia histórica';
