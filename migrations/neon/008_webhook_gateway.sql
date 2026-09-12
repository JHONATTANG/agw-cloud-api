-- ============================================================
--  008_webhook_gateway.sql — La nube avisa al gateway
-- ============================================================
--  Hasta ahora el gateway preguntaba cada 5 s si había órdenes, y la
--  respuesta era «no» 17.000 veces al día. Eso mantenía la base
--  despierta el 100 % del tiempo y no compraba nada: la orden llegaba
--  en 5 s porque se preguntaba cada 5 s.
--
--  Se invierte: el gateway anuncia una URL pública (Tailscale Funnel)
--  donde recibir avisos, y la API le hace un POST firmado en el momento
--  de encolar una orden. El sondeo queda como red de seguridad cada
--  10 minutos, por si el aviso no llega.
--
--  La URL vive en la fila del gateway y no en una variable de entorno:
--  la anuncia el propio gateway al arrancar, así que si cambia (otro
--  tailnet, otro puerto) no hay que tocar nada en Vercel. El secreto
--  con que se firma sí es variable de entorno (GATEWAY_WEBHOOK_SECRET):
--  un secreto no se guarda en la base.

ALTER TABLE public.gateways
    ADD COLUMN IF NOT EXISTS webhook_url TEXT,
    ADD COLUMN IF NOT EXISTS webhook_anunciado_en TIMESTAMPTZ;

COMMENT ON COLUMN public.gateways.webhook_url IS
    'URL publica donde el gateway recibe avisos firmados (POST). La '
    'anuncia el gateway en /api/iot/gateway/webhook. NULL = solo sondeo.';

-- Cómo le fue a cada aviso, para que el panel diga «entregada al
-- instante» o «en cola, la recogerá el sondeo» sin adivinar.
ALTER TABLE public.comandos
    ADD COLUMN IF NOT EXISTS aviso TEXT
        CHECK (aviso IN ('entregado', 'fallido', 'sin_webhook'));

COMMENT ON COLUMN public.comandos.aviso IS
    'Resultado del webhook al gateway al encolar: entregado, fallido '
    'o sin_webhook (el gateway no ha anunciado URL).';
