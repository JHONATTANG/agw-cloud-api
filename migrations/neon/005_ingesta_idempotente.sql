-- ============================================================
--  005_ingesta_idempotente.sql
-- ============================================================
--  El indice unico lo creaba a mano el script de carga historica, asi
--  que no estaba en ninguna migracion: una base recreada desde cero no
--  lo tendria y la ingesta dejaria de ser idempotente sin que nada lo
--  avisara.
--
--  Por que hace falta: el gateway reintenta los envios que no confirma,
--  y guarda su buffer hasta recibir el acuse. Sin una clave que
--  identifique la trama, un reintento tras una respuesta perdida crea
--  un duplicado. Con ella, reenviar es inofensivo — y eso es lo que
--  permite que la Raspberry se sincronice sola sin marcar nada a mano.
--
--  La clave es (sensor_id, t_rx): un nodo no puede emitir dos tramas en
--  el mismo microsegundo, y t_rx lo sella el gateway al recibir.
-- ============================================================

CREATE UNIQUE INDEX IF NOT EXISTS uq_telemetria_sensor_trx
    ON public.telemetria_indoor (sensor_id, t_rx)
    WHERE t_rx IS NOT NULL;

COMMENT ON INDEX public.uq_telemetria_sensor_trx IS
    'Identidad de una trama. Permite que POST /api/telemetria sea '
    'idempotente: un reenvio del gateway no duplica.';
