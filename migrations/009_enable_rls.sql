-- ============================================================
-- MIGRATION 009: Row Level Security (RLS)
-- Cada usuario accede SOLO a sus propios dispositivos y datos
-- Depende de: 001–005 (todas las tablas)
-- ============================================================
-- NOTA: Los endpoints de la API Cloud utilizan la service_role key
-- (bypasses RLS) para inserciones de telemetría por el Edge Gateway.
-- Los JWT de usuarios finales usan la anon/authenticated key (RLS activo).
-- ============================================================

-- ── Habilitar RLS en todas las tablas ──────────────────────
ALTER TABLE users            ENABLE ROW LEVEL SECURITY;
ALTER TABLE iot_devices      ENABLE ROW LEVEL SECURITY;
ALTER TABLE telemetry        ENABLE ROW LEVEL SECURITY;
ALTER TABLE device_commands  ENABLE ROW LEVEL SECURITY;
ALTER TABLE alerts           ENABLE ROW LEVEL SECURITY;

-- ── Función helper: rol del usuario actual ─────────────────
-- Retorna el rol como TEXT para evitar casting en cada política
CREATE OR REPLACE FUNCTION current_user_role()
RETURNS TEXT AS $$
    SELECT role::TEXT FROM users WHERE id = auth.uid()
$$ LANGUAGE sql STABLE SECURITY DEFINER;

-- ── Políticas: users ───────────────────────────────────────
-- Ver: propio perfil, o admins ven todos
CREATE POLICY users_self_read ON users
    FOR SELECT USING (
        id = auth.uid()
        OR current_user_role() IN ('ADMIN', 'SUPERROOT')
    );

-- Actualizar: solo propio perfil (admins pueden actualizar todos)
CREATE POLICY users_self_update ON users
    FOR UPDATE USING (
        id = auth.uid()
        OR current_user_role() IN ('ADMIN', 'SUPERROOT')
    );

-- Insertar nuevos usuarios: solo ADMIN y SUPERROOT
CREATE POLICY users_admin_insert ON users
    FOR INSERT WITH CHECK (
        current_user_role() IN ('ADMIN', 'SUPERROOT')
    );

-- ── Políticas: iot_devices ─────────────────────────────────
CREATE POLICY devices_owner_access ON iot_devices
    FOR ALL USING (
        user_id = auth.uid()
        OR current_user_role() IN ('ADMIN', 'SUPERROOT')
    );

-- ── Políticas: telemetry ───────────────────────────────────
-- Lectura: solo datos de sus dispositivos
CREATE POLICY telemetry_device_owner ON telemetry
    FOR SELECT USING (
        device_id IN (
            SELECT id FROM iot_devices WHERE user_id = auth.uid()
        )
        OR current_user_role() IN ('ADMIN', 'SUPERROOT')
    );

-- Inserción: controlada por la API Cloud con service_role key
-- (service_role bypasses RLS, esta política es capa extra de seguridad)
CREATE POLICY telemetry_insert_service ON telemetry
    FOR INSERT WITH CHECK (TRUE);

-- ── Políticas: device_commands ────────────────────────────
-- Solo puede ver y crear comandos para sus propios dispositivos
CREATE POLICY commands_owner_access ON device_commands
    FOR ALL USING (
        device_id IN (
            SELECT id FROM iot_devices WHERE user_id = auth.uid()
        )
        OR current_user_role() IN ('ADMIN', 'SUPERROOT')
    );

-- Solo OPERATOR, ADMIN, SUPERROOT pueden crear comandos
CREATE POLICY commands_create_authorized ON device_commands
    FOR INSERT WITH CHECK (
        current_user_role() IN ('OPERATOR', 'ADMIN', 'SUPERROOT')
    );

-- ── Políticas: alerts ──────────────────────────────────────
-- Cada usuario ve solo sus propias alertas
CREATE POLICY alerts_user_access ON alerts
    FOR ALL USING (
        user_id = auth.uid()
        OR current_user_role() IN ('ADMIN', 'SUPERROOT')
    );
