-- migrations/02_users_and_devices.sql
-- ---------------------------------------------------------------------------
-- Noxum Soluciones - AGW Cloud API
-- Módulo de Usuarios, Dispositivos (Asignaciones) y Auth Passwordless
-- ---------------------------------------------------------------------------

-- 1. EXTENSIONES NECESARIAS
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 2. TABLA: users
CREATE TABLE IF NOT EXISTS public.users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email VARCHAR(255) UNIQUE NOT NULL,
    full_name VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 3. TABLA: auth_codes (OTPs temporales para Passwordless)
CREATE TABLE IF NOT EXISTS public.auth_codes (
    id SERIAL PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    otp_code VARCHAR(10) NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    used BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Indexar código y usuario para consultas rápidad al validar
CREATE INDEX IF NOT EXISTS idx_auth_codes_user_unused ON public.auth_codes (user_id, otp_code) WHERE used = FALSE;

-- 4. TABLA: device_assignments (Dueños de dispositivos/nodos)
-- Nota: node_id se asocia como texto libre ya que es generado por el Gateway y puede o no pre-existir en telemetría.
CREATE TABLE IF NOT EXISTS public.device_assignments (
    id SERIAL PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    node_id VARCHAR(100) NOT NULL,
    alias VARCHAR(255),
    assigned_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, node_id) -- Un usuario no puede tener el mismo nodo mapeado dos veces (opcional, pero buena práctica)
);

-- ---------------------------------------------------------------------------
-- 5. SEED: Creación del Usuario Inicial y Asignación de Dispositivos Reales
-- Requerimiento: jhonattan.gonzalez.38@gmail.com
--                1 Gateway Broker
--                1 Nodo Tierra (temperatura, humedad, humedad_suelo)
--                1 Nodo Hidroponía (temperatura, humedad, ph)
-- ---------------------------------------------------------------------------

DO $$
DECLARE
    new_user_id UUID;
BEGIN
    -- Crear/Asegurar usuario jhonattan.gonzalez.38@gmail.com
    INSERT INTO public.users (email, full_name)
    VALUES ('jhonattan.gonzalez.38@gmail.com', 'Jhonattan Gonzalez')
    ON CONFLICT (email) DO UPDATE 
    SET full_name = EXCLUDED.full_name
    RETURNING id INTO new_user_id;

    -- Asignación de Broker (Gateway Principal)
    INSERT INTO public.device_assignments (user_id, node_id, alias)
    VALUES (new_user_id, 'FOG_RPI_VITALCROP_01', 'Gateway IoT Principal')
    ON CONFLICT (user_id, node_id) DO NOTHING;

    -- Asignación de Nodo de Tierra
    INSERT INTO public.device_assignments (user_id, node_id, alias)
    VALUES (new_user_id, 'ESP32_SOIL_NODE_A', 'Nodo de Suelo (Tierra)')
    ON CONFLICT (user_id, node_id) DO NOTHING;

    -- Asignación de Nodo Hidroponía
    INSERT INTO public.device_assignments (user_id, node_id, alias)
    VALUES (new_user_id, 'ESP32_HYDRO_NODE_A', 'Nodo Hidropónico')
    ON CONFLICT (user_id, node_id) DO NOTHING;

    RAISE NOTICE 'Seed de usuario exitoso. ID: %', new_user_id;
END $$;
