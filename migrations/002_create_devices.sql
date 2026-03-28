-- ============================================================
-- MIGRATION 002: iot_devices
-- Nodos ESP32 registrados en el sistema VitalCrop AGW
-- Depende de: 001_create_users.sql
-- ============================================================

CREATE TYPE device_type   AS ENUM ('SOIL', 'HYDRO');
CREATE TYPE device_status AS ENUM ('ONLINE', 'OFFLINE', 'MAINTENANCE', 'ERROR');

CREATE TABLE iot_devices (
    id               UUID           PRIMARY KEY DEFAULT gen_random_uuid(),
    device_uid       TEXT           UNIQUE NOT NULL,        -- AGW-SOIL-01, AGW-HYDRO-01
    device_type      device_type    NOT NULL,
    location         TEXT,
    description      TEXT,
    firmware_version TEXT,
    user_id          UUID           NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    gateway_id       TEXT,                                  -- ID del Edge Gateway al que pertenece
    status           device_status  NOT NULL DEFAULT 'OFFLINE',
    is_active        BOOLEAN        NOT NULL DEFAULT TRUE,
    last_seen        TIMESTAMPTZ,
    ip_address       INET,                                  -- IP asignada en red IoT privada
    mac_address      MACADDR,
    config           JSONB          NOT NULL DEFAULT '{}',  -- Configuración dinámica del nodo
    created_at       TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ    NOT NULL DEFAULT NOW()
);

CREATE TRIGGER devices_updated_at
    BEFORE UPDATE ON iot_devices
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- -------------------------------------------------------
-- Comentarios
-- -------------------------------------------------------
COMMENT ON TABLE  iot_devices             IS 'Dispositivos IoT (nodos ESP32) registrados en la plataforma';
COMMENT ON COLUMN iot_devices.device_uid  IS 'Identificador único del firmware: AGW-SOIL-01, AGW-HYDRO-01';
COMMENT ON COLUMN iot_devices.gateway_id  IS 'ID del Raspberry Pi Edge Gateway que gestiona este nodo';
COMMENT ON COLUMN iot_devices.config      IS 'Configuración dinámica: umbrales de sensor, intervalos de reporte, etc.';
COMMENT ON COLUMN iot_devices.ip_address  IS 'IP asignada por dnsmasq en la red privada 192.168.10.0/24';
