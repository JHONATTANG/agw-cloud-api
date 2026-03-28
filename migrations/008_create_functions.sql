-- ============================================================
-- MIGRATION 008: functions
-- Funciones de utilidad para el dashboard y la API Cloud
-- Depende de: 003_create_telemetry.sql, 002_create_devices.sql
-- ============================================================

-- ── Función: telemetría agregada en buckets de tiempo ──────
-- Utilizada por los endpoints /telemetry/chart de la API Cloud
-- Permite granularidad variable: 5min, 15min, 1h, etc.
CREATE OR REPLACE FUNCTION get_telemetry_bucketed(
    p_device_id  UUID,
    p_from       TIMESTAMPTZ,
    p_to         TIMESTAMPTZ,
    p_bucket     INTERVAL DEFAULT '15 minutes'
)
RETURNS TABLE (
    bucket        TIMESTAMPTZ,
    avg_temp      NUMERIC,
    avg_humidity  NUMERIC,
    avg_moisture  NUMERIC,
    avg_ph        NUMERIC,
    avg_ec        NUMERIC,
    avg_water_temp NUMERIC,
    avg_water_level NUMERIC,
    record_count  BIGINT
) AS $$
    SELECT
        -- Truncar al inicio del bucket de tiempo
        date_trunc('hour', timestamp) +
            (EXTRACT(MINUTE FROM timestamp)::INT
             / EXTRACT(MINUTE FROM p_bucket)::INT)
            * p_bucket                           AS bucket,

        AVG(temperature)::NUMERIC(6,2)           AS avg_temp,
        AVG(humidity)::NUMERIC(5,2)              AS avg_humidity,
        AVG(soil_moisture)::NUMERIC(5,2)         AS avg_moisture,
        AVG(ph)::NUMERIC(5,2)                    AS avg_ph,
        AVG(ec)::NUMERIC(7,3)                    AS avg_ec,
        AVG(water_temp)::NUMERIC(6,2)            AS avg_water_temp,
        AVG(water_level)::NUMERIC(5,2)           AS avg_water_level,
        COUNT(*)                                 AS record_count

    FROM telemetry
    WHERE device_id = p_device_id
      AND timestamp BETWEEN p_from AND p_to
    GROUP BY 1
    ORDER BY 1;
$$ LANGUAGE sql STABLE;

COMMENT ON FUNCTION get_telemetry_bucketed IS
    'Retorna telemetría agregada en buckets de tiempo configurables. Uso: GET /telemetry/chart';


-- ── Función: estadísticas rápidas de los últimos 7 días ────
-- Utilizada por las tarjetas de resumen en el dashboard
CREATE OR REPLACE FUNCTION get_device_stats(p_device_id UUID)
RETURNS JSONB AS $$
DECLARE
    result JSONB;
BEGIN
    SELECT jsonb_build_object(
        'total_records',     COUNT(*),
        'period_days',       7,
        'first_record',      MIN(timestamp),
        'last_record',       MAX(timestamp),
        'avg_temperature',   ROUND(AVG(temperature)::NUMERIC, 2),
        'min_temperature',   ROUND(MIN(temperature)::NUMERIC, 2),
        'max_temperature',   ROUND(MAX(temperature)::NUMERIC, 2),
        'avg_humidity',      ROUND(AVG(humidity)::NUMERIC, 2),
        'avg_soil_moisture', ROUND(AVG(soil_moisture)::NUMERIC, 2),
        'avg_ph',            ROUND(AVG(ph)::NUMERIC, 2),
        'min_ph',            ROUND(MIN(ph)::NUMERIC, 2),
        'max_ph',            ROUND(MAX(ph)::NUMERIC, 2),
        'avg_ec',            ROUND(AVG(ec)::NUMERIC, 3),
        'avg_water_level',   ROUND(AVG(water_level)::NUMERIC, 2)
    )
    INTO result
    FROM telemetry
    WHERE device_id = p_device_id
      AND timestamp > NOW() - INTERVAL '7 days';

    RETURN COALESCE(result, '{}'::JSONB);
END;
$$ LANGUAGE plpgsql STABLE;

COMMENT ON FUNCTION get_device_stats IS
    'Retorna estadísticas de los últimos 7 días en JSONB. Uso: GET /devices/{id}/stats';


-- ── Función: marcar alertas como leídas en lote ────────────
CREATE OR REPLACE FUNCTION mark_alerts_read(p_user_id UUID, p_alert_ids UUID[])
RETURNS INTEGER AS $$
DECLARE
    updated_count INTEGER;
BEGIN
    UPDATE alerts
    SET is_read = TRUE,
        read_at  = NOW()
    WHERE user_id    = p_user_id
      AND id         = ANY(p_alert_ids)
      AND is_read    = FALSE;

    GET DIAGNOSTICS updated_count = ROW_COUNT;
    RETURN updated_count;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION mark_alerts_read IS
    'Marca un array de alertas como leídas en una sola operación. Retorna el número de alertas actualizadas.';
