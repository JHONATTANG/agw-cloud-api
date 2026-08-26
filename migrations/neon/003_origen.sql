-- ============================================================
--  003_origen.sql — Distinguir el dato en vivo del relleno
-- ============================================================
--  Los 31.776 registros históricos de la Raspberry se insertan de
--  golpe, hoy. Sus `created_at` son de hoy y sus `t_rx` de hace hasta
--  17 días, así que la latencia de subida calculada sobre ellos daría
--  cientos de horas.
--
--  Falsear `created_at` para que cuadre sería inventar una medición.
--  La alternativa correcta es marcar el origen: el dato histórico es
--  igual de válido para temperatura, RSSI o pérdida —se midió cuando
--  se midió— y solo debe excluirse de las métricas que dependen del
--  instante de INSERCIÓN, que son las de subida a la nube.
-- ============================================================

ALTER TABLE public.telemetria_indoor
    ADD COLUMN IF NOT EXISTS origen VARCHAR(12) NOT NULL DEFAULT 'directo';

COMMENT ON COLUMN public.telemetria_indoor.origen IS
    'directo = ingesta en tiempo real desde el gateway. '
    'backfill = carga histórica; su created_at no sirve para medir latencia';

CREATE INDEX IF NOT EXISTS idx_telemetria_origen
    ON public.telemetria_indoor (origen, t_rx DESC);

-- La vista de latencia solo mira el flujo en vivo. Con el filtro
-- dentro de la vista, ninguna consulta del dashboard puede olvidarse
-- de aplicarlo.
CREATE OR REPLACE VIEW public.v_latencia_subida AS
SELECT
    t_rx,
    sensor_id,
    EXTRACT(EPOCH FROM (created_at - t_rx)) * 1000 AS latencia_ms
FROM public.telemetria_indoor
WHERE t_rx IS NOT NULL
  AND created_at > t_rx
  AND origen = 'directo';
