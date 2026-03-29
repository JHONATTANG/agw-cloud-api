-- ==========================================
-- 1. DROP OLD TABLE AND CREATE NEW ONES
-- ==========================================

DROP TABLE IF EXISTS public.device_assignments CASCADE;

-- Tabla: gateways (Broker principal asignado a un usuario)
CREATE TABLE IF NOT EXISTS public.gateways (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    gateway_id VARCHAR NOT NULL,
    alias VARCHAR,
    created_at TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT unique_user_gateway UNIQUE (user_id, gateway_id)
);

-- Tabla: edge_nodes (Nodos ESP32 de Tierra o Hidroponía conectados a un gateway)
CREATE TABLE IF NOT EXISTS public.edge_nodes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    gateway_id UUID NOT NULL REFERENCES public.gateways(id) ON DELETE CASCADE,
    sensor_id VARCHAR NOT NULL,
    node_type VARCHAR NOT NULL CHECK (node_type IN ('TIERRA', 'HIDROPONIA')),
    alias VARCHAR,
    created_at TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT unique_gateway_sensor UNIQUE (gateway_id, sensor_id)
);

-- ==========================================
-- 2. ÍNDICES
-- ==========================================

CREATE INDEX IF NOT EXISTS gateways_user_id_idx 
ON public.gateways (user_id);

CREATE INDEX IF NOT EXISTS edge_nodes_gateway_id_idx 
ON public.edge_nodes (gateway_id);

-- ==========================================
-- 3. DATOS SEMILLA (SEED DATA)
-- ==========================================

DO $$
DECLARE
    v_user_id UUID;
    v_target_email VARCHAR := 'jhonattan.gonzalez.38@gmail.com';
    v_gateway_uuid UUID;
    v_gateway_id VARCHAR := 'FOG_RPI_HIERBABUENA_01';
BEGIN
    -- 1. Insertar el Usuario
    INSERT INTO public.users (email, full_name)
    VALUES (v_target_email, 'Jhonattan Gonzalez')
    ON CONFLICT (email) DO UPDATE 
    SET full_name = EXCLUDED.full_name
    RETURNING id INTO v_user_id;

    IF v_user_id IS NULL THEN
        SELECT id INTO v_user_id FROM public.users WHERE email = v_target_email;
    END IF;

    -- 2. Insertar el Gateway (Dispositivo Broker)
    INSERT INTO public.gateways (user_id, gateway_id, alias)
    VALUES (v_user_id, v_gateway_id, 'Broker Principal - Vital Crop AGW')
    ON CONFLICT (user_id, gateway_id) DO UPDATE 
    SET alias = EXCLUDED.alias
    RETURNING id INTO v_gateway_uuid;

    IF v_gateway_uuid IS NULL THEN
        SELECT id INTO v_gateway_uuid FROM public.gateways WHERE user_id = v_user_id AND gateway_id = v_gateway_id;
    END IF;

    -- 3. Insertar los Nodos (ESP32)
    -- Tierra
    INSERT INTO public.edge_nodes (gateway_id, sensor_id, node_type, alias)
    VALUES (v_gateway_uuid, 'ESP32_TIERRA_01', 'TIERRA', 'Nodo Sensor Tierra 1')
    ON CONFLICT (gateway_id, sensor_id) DO UPDATE 
    SET alias = EXCLUDED.alias, node_type = EXCLUDED.node_type;

    -- Hidroponía
    INSERT INTO public.edge_nodes (gateway_id, sensor_id, node_type, alias)
    VALUES (v_gateway_uuid, 'ESP32_HIDROPONIA_01', 'HIDROPONIA', 'Nodo Sensor Hidroponía 1')
    ON CONFLICT (gateway_id, sensor_id) DO UPDATE 
    SET alias = EXCLUDED.alias, node_type = EXCLUDED.node_type;

    -- 4. Opcional: Insertar telemetría de prueba con estos nuevos sensor_ids
    IF NOT EXISTS (SELECT 1 FROM public.telemetria_indoor WHERE node_id = v_gateway_id AND sensor_id = 'ESP32_TIERRA_01' LIMIT 1) THEN
        -- Lectura de TIERRA
        INSERT INTO public.telemetria_indoor (
            node_id, sensor_id, temperatura, humedad_ambiente, humedad_suelo, estado_actuadores
        ) VALUES 
        (v_gateway_id, 'ESP32_TIERRA_01', 22.5, 65.0, 70.0, '{"valvula_agua": "ON"}');
    END IF;

    IF NOT EXISTS (SELECT 1 FROM public.telemetria_indoor WHERE node_id = v_gateway_id AND sensor_id = 'ESP32_HIDROPONIA_01' LIMIT 1) THEN
        -- Lectura de HIDROPONÍA
        INSERT INTO public.telemetria_indoor (
            node_id, sensor_id, temperatura, humedad_ambiente, ph, estado_actuadores
        ) VALUES 
        (v_gateway_id, 'ESP32_HIDROPONIA_01', 23.1, 63.5, 6.1, '{"bomba_nutrientes": "ON", "oxigenador": "ON"}');
    END IF;

END $$;
