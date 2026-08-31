-- ============================================================
--  006_nodos_simulados.sql — Separar lo medido de lo generado
-- ============================================================
--  El banco de pruebas incorpora un segundo nodo cuyos sensores no
--  existen: el ESP32 genera los valores dentro de sí mismo. Sirve para
--  dos cosas legítimas — probar la capacidad multinodo del punto de
--  acceso y poblar la vista de varios cultivos — y no hay ningún
--  problema en presentarlo como un cultivo más en la interfaz.
--
--  El problema sería otro: que sus tramas entren indistinguibles de las
--  del nodo real en las métricas de telecomunicaciones. La pérdida, el
--  jitter y el RSSI que el proyecto defiende describen UN enlace físico
--  medido durante semanas. Promediarlo con un generador de tráfico no
--  daría una cifra peor ni mejor: daría una cifra que no describe nada,
--  y que no se podría defender si alguien pregunta de dónde sale.
--
--  De ahí la separación. La bandera vive en el nodo, no en cada trama,
--  porque lo sintético es el aparato y no la fila: una fila no puede
--  volverse real, un nodo sí puede dejar de simular.

ALTER TABLE public.edge_nodes
    ADD COLUMN IF NOT EXISTS simulado BOOLEAN NOT NULL DEFAULT false;

COMMENT ON COLUMN public.edge_nodes.simulado IS
    'true = los sensores no existen; el firmware genera los valores. '
    'Se excluye de las metricas de telecomunicaciones del MCD §9.';

-- ------------------------------------------------------------
--  Vista de telemetría real
-- ------------------------------------------------------------
--  Un único sitio donde se decide qué cuenta como medición. La
--  alternativa —añadir el filtro a cada consulta de métricas— garantiza
--  que tarde o temprano una se quede sin él, y ese fallo es silencioso:
--  el número sale, solo que está mal.
--
--  LEFT JOIN y no INNER: una trama de un sensor que todavía no está
--  dado de alta en `edge_nodes` es real hasta que se demuestre lo
--  contrario. Con INNER desaparecería sin avisar.

CREATE OR REPLACE VIEW public.telemetria_real AS
    SELECT t.*
    FROM public.telemetria_indoor t
    LEFT JOIN public.edge_nodes n ON n.sensor_id = t.sensor_id
    WHERE COALESCE(n.simulado, false) = false;

COMMENT ON VIEW public.telemetria_real IS
    'telemetria_indoor sin los nodos simulados. Es la fuente de las '
    'metricas del §9; el panel de cultivos usa la tabla completa.';

-- ------------------------------------------------------------
--  Alta del segundo nodo
-- ------------------------------------------------------------
--  Cuelga del mismo gateway: es la misma Raspberry y el mismo punto de
--  acceso. Lo que cambia es el cultivo y que sus datos son sintéticos.

INSERT INTO public.edge_nodes (gateway_id, sensor_id, node_type, alias, simulado)
SELECT g.id, 'IoT-node-26.002', 'HIDROPONIA',
       'Nodo HydroNode · lechuga hidropónica', true
FROM public.gateways g
WHERE g.gateway_id = 'FOG_RPI_HIERBABUENA_01'
ON CONFLICT (gateway_id, sensor_id) DO NOTHING;

INSERT INTO public.schema_migrations (filename, checksum, applied_at)
VALUES ('006_nodos_simulados.sql', 'manual', now())
ON CONFLICT DO NOTHING;
