"""
Aviso firmado al gateway.

La nube no puede entrar a la red del cultivo, pero el gateway expone una
URL pública por Tailscale Funnel y la anuncia aquí. Cuando el panel
encola una orden, la API le hace un POST a esa URL con un mensaje corto
—«hay órdenes para este nodo»— y el gateway sale a buscarlas en el
acto. El mensaje no lleva la orden: la fuente de verdad sigue siendo la
tabla `comandos`, y el gateway la lee y la marca como siempre. Así un
aviso perdido no pierde nada (el sondeo cada 10 min la recoge) y un
aviso duplicado no duplica nada.

FIRMA

HMAC-SHA256 sobre `timestamp.cuerpo` con un secreto compartido
(GATEWAY_WEBHOOK_SECRET). El gateway rechaza firmas malas y
timestamps a más de 5 min: una petición capturada no sirve después.
Que la URL sea pública no importa mientras el secreto no lo sea.

TIEMPO

El POST se hace dentro de la petición, antes de responder al panel,
porque Vercel congela la función al responder y un envío «en segundo
plano» no se ejecutaría. Tope de 4 s: si el gateway no contesta, la
orden queda en cola con aviso='fallido' y el panel lo dice.

`urllib` y no httpx, por la misma razón que en email_otp: una llamada
no justifica una dependencia en el bundle.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
import urllib.error
import urllib.request

logger = logging.getLogger("agw-cloud-api.webhook")

_TIMEOUT_S = 4.0


def firmar(secreto: str, timestamp: str, cuerpo: bytes) -> str:
    return hmac.new(secreto.encode(), f"{timestamp}.".encode() + cuerpo, hashlib.sha256).hexdigest()


def avisar_gateway(url: str | None, gateway_id: str, sensor_ids: list[str],
                   motivo: str = "ordenes") -> str:
    """
    Devuelve 'entregado', 'fallido' o 'sin_webhook'. Nunca lanza: un
    gateway apagado no puede impedir que la orden se encole.
    """
    if not url:
        return "sin_webhook"
    secreto = os.getenv("GATEWAY_WEBHOOK_SECRET", "")
    if not secreto:
        logger.warning("GATEWAY_WEBHOOK_SECRET no definido: no se avisa al gateway")
        return "sin_webhook"

    ts = str(int(time.time()))
    cuerpo = json.dumps({"gateway_id": gateway_id, "motivo": motivo,
                         "sensor_ids": sensor_ids, "ts": int(ts)}).encode()
    req = urllib.request.Request(
        url.rstrip("/") + "/webhook/ordenes", data=cuerpo, method="POST",
        headers={
            "Content-Type": "application/json",
            "X-AGW-Timestamp": ts,
            "X-AGW-Signature": firmar(secreto, ts, cuerpo),
            "User-Agent": "agw-cloud-api/webhook",
        },
    )
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT_S) as r:
            ok = 200 <= r.status < 300
        logger.info("Aviso al gateway %s: %s en %.0f ms", gateway_id,
                    "ok" if ok else f"HTTP {r.status}", (time.monotonic() - t0) * 1000)
        return "entregado" if ok else "fallido"
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
        logger.warning("Aviso al gateway %s fallido tras %.0f ms: %s", gateway_id,
                       (time.monotonic() - t0) * 1000, exc)
        return "fallido"
