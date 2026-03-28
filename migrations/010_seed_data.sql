-- ============================================================
-- MIGRATION 010: seed_data
-- Datos iniciales para desarrollo y producción
-- Depende de: 001_create_users.sql, 002_create_devices.sql
-- ============================================================
-- IMPORTANTE: Cambiar la contraseña del admin en producción
-- Hash generado con: bcrypt.hash('VitalCrop2024!', 12)
-- Contraseña por defecto:  VitalCrop2024!
-- ============================================================

-- ── Usuario administrador por defecto ──────────────────────
INSERT INTO users (id, email, password_hash, full_name, role)
VALUES (
    gen_random_uuid(),
    'admin@vitalcrop.io',
    -- bcrypt hash de 'VitalCrop2024!'  (rounds=12)
    '$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjPGga31lW',
    'VitalCrop Admin',
    'SUPERROOT'
);

-- ── Dispositivos de ejemplo vinculados al admin ─────────────
WITH admin AS (
    SELECT id FROM users WHERE email = 'admin@vitalcrop.io'
)
INSERT INTO iot_devices (
    device_uid, device_type, location, description,
    user_id, gateway_id, status, config
)
SELECT
    devs.device_uid,
    devs.device_type::device_type,
    devs.location,
    devs.description,
    admin.id,
    'AGW-EDGE-01',
    'OFFLINE',
    devs.config::JSONB
FROM admin,
(VALUES
    (
        'AGW-SOIL-01',
        'SOIL',
        'Greenhouse A — Sector Norte',
        'Nodo SOIL: temperatura, humedad, humedad de suelo y control de bomba',
        '{"report_interval_s": 30, "thresholds": {"soil_moisture_min": 30, "temperature_max": 35}}'
    ),
    (
        'AGW-HYDRO-01',
        'HYDRO',
        'Greenhouse A — Sistema Hidropónico',
        'Nodo HYDRO: pH, EC, temperatura y nivel de agua',
        '{"report_interval_s": 30, "thresholds": {"ph_min": 5.5, "ph_max": 7.0, "ec_max": 3.0}}'
    )
) AS devs(device_uid, device_type, location, description, config);

-- ── Alerta de ejemplo (sirve para confirmar el schema) ─────
WITH
    admin   AS (SELECT id FROM users       WHERE email      = 'admin@vitalcrop.io'),
    device  AS (SELECT id FROM iot_devices WHERE device_uid = 'AGW-SOIL-01')
INSERT INTO alerts (device_id, user_id, alert_type, severity, source, message, context)
SELECT
    device.id,
    admin.id,
    'SYSTEM_STARTUP',
    'INFO',
    'SYSTEM',
    'Sistema VitalCrop AGW inicializado correctamente.',
    '{"version": "1.0.0", "migration": "010_seed_data"}'
FROM admin, device;
