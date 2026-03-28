-- ============================================================
-- MIGRATION: telemetria_indoor
-- Sistema de monitoreo hidropónico de hierbabuena
-- Compatible con Supabase (PostgreSQL 15+)
-- Ejecutar en: Supabase → SQL Editor
-- ============================================================

-- ── Tabla principal ────────────────────────────────────────
CREATE TABLE IF NOT EXISTS telemetria_indoor (
    id                  BIGSERIAL       PRIMARY KEY,
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    -- Identificación del nodo y sensor
    node_id             TEXT            NOT NULL,   -- ej. "FOG_RPI_HIERBABUENA_01"
    sensor_id           TEXT            NOT NULL,   -- ej. "ESP32_ZONA_A"

    -- Parámetros ambientales
    temperatura         REAL,                       -- °C   (rango típico hierbabuena: 18–28 °C)
    humedad_ambiente    REAL,                       -- %    (rango típico: 50–70 %)

    -- Parámetros de la solución nutritiva / sustrato
    humedad_suelo       REAL,                       -- %    (sustrato/reservorio: 70–90 %)
    ph                  REAL,                       -- 0–14 (óptimo hierbabuena: 5.5–6.5)

    -- Estado de actuadores (JSON serializado como texto)
    -- Ejemplo: '{"bomba": "ON", "lampara": "ON", "ventilador": "OFF"}'
    estado_actuadores   TEXT,

    -- Constrains de integridad de dominio
    CONSTRAINT chk_temperatura      CHECK (temperatura      BETWEEN -40   AND 100),
    CONSTRAINT chk_humedad_ambiente CHECK (humedad_ambiente BETWEEN 0     AND 100),
    CONSTRAINT chk_humedad_suelo    CHECK (humedad_suelo    BETWEEN 0     AND 100),
    CONSTRAINT chk_ph               CHECK (ph               BETWEEN 0     AND 14)
);

-- ── Comentarios de documentación ──────────────────────────
COMMENT ON TABLE  telemetria_indoor                  IS 'Telemetría de sensores IoT para cultivo hidropónico indoor de hierbabuena.';
COMMENT ON COLUMN telemetria_indoor.id               IS 'PK auto-incremental.';
COMMENT ON COLUMN telemetria_indoor.created_at       IS 'Timestamp de ingesta en la base de datos (UTC).';
COMMENT ON COLUMN telemetria_indoor.node_id          IS 'ID del Gateway/Fog Node (Raspberry Pi).';
COMMENT ON COLUMN telemetria_indoor.sensor_id        IS 'ID del nodo sensor ESP32 origen.';
COMMENT ON COLUMN telemetria_indoor.temperatura      IS 'Temperatura ambiente en grados Celsius.';
COMMENT ON COLUMN telemetria_indoor.humedad_ambiente IS 'Humedad relativa del aire en porcentaje.';
COMMENT ON COLUMN telemetria_indoor.humedad_suelo    IS 'Humedad del sustrato o solución nutritiva en porcentaje.';
COMMENT ON COLUMN telemetria_indoor.ph               IS 'Nivel de pH de la solución nutritiva (óptimo hierbabuena: 5.5–6.5).';
COMMENT ON COLUMN telemetria_indoor.estado_actuadores IS 'Estado JSON de actuadores activos en el momento de la lectura.';

-- ── Índices de optimización ────────────────────────────────

-- Índice 1: Consultas por nodo (endpoint GET /api/telemetria/{node_id})
CREATE INDEX IF NOT EXISTS idx_telemetria_indoor_node_id
    ON telemetria_indoor (node_id);

-- Índice 2: Consultas por time range (dashboards, alertas, históricos)
CREATE INDEX IF NOT EXISTS idx_telemetria_indoor_created_at
    ON telemetria_indoor (created_at DESC);

-- Índice 3: Índice compuesto — filrar por nodo Y ordenar por tiempo (query principal)
CREATE INDEX IF NOT EXISTS idx_telemetria_indoor_node_time
    ON telemetria_indoor (node_id, created_at DESC);

-- Índice 4: Consultas por sensor específico dentro de un nodo
CREATE INDEX IF NOT EXISTS idx_telemetria_indoor_sensor_id
    ON telemetria_indoor (sensor_id);

-- ── Row Level Security (opcional — recomendar para Supabase) ──
-- Habilitar RLS para controlar acceso desde el frontend JS SDK
-- ALTER TABLE telemetria_indoor ENABLE ROW LEVEL SECURITY;
--
-- Política de lectura pública (si se usa con anon key en el dashboard):
-- CREATE POLICY "Lectura para usuarios autenticados"
--   ON telemetria_indoor FOR SELECT
--   USING (auth.role() = 'authenticated');
--
-- Política de inserción solo mediante service_role (API backend):
-- CREATE POLICY "Solo service_role puede insertar"
--   ON telemetria_indoor FOR INSERT
--   WITH CHECK (auth.role() = 'service_role');

-- ── Datos de prueba (seed) ─────────────────────────────────
-- Descomentar para poblar datos de ejemplo en desarrollo

/*
INSERT INTO telemetria_indoor
    (node_id, sensor_id, temperatura, humedad_ambiente, humedad_suelo, ph, estado_actuadores)
VALUES
    ('FOG_RPI_HIERBABUENA_01', 'ESP32_ZONA_A', 23.5, 65.2, 82.0, 6.1, '{"bomba": "ON", "lampara": "ON", "ventilador": "OFF"}'),
    ('FOG_RPI_HIERBABUENA_01', 'ESP32_ZONA_A', 23.8, 64.9, 81.5, 6.0, '{"bomba": "ON", "lampara": "ON", "ventilador": "OFF"}'),
    ('FOG_RPI_HIERBABUENA_01', 'ESP32_ZONA_B', 22.9, 66.1, 83.2, 5.9, '{"bomba": "OFF", "lampara": "ON", "ventilador": "ON"}'),
    ('FOG_RPI_HIERBABUENA_01', 'ESP32_ZONA_B', 22.5, 67.0, 84.0, 5.8, '{"bomba": "OFF", "lampara": "ON", "ventilador": "ON"}');
*/
