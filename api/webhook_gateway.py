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

DNS

El resolver del runtime de Python en Vercel no resuelve los nombres
`*.ts.net` de Funnel: `getaddrinfo` devuelve `[Errno 16] Device or
resource busy` mientras cualquier otro dominio resuelve bien. Se
comprobó paso a paso (DNS, TCP, TLS, urllib) y falla en el primero.
Por eso hay un camino de respaldo: resolver por DNS sobre HTTPS
(Google, y Cloudflare si falla) y conectar a la IP con SNI y `Host`
del nombre real, que es lo que el certificado y Funnel esperan. La IP
se recuerda 10 min por instancia de la función.

TIEMPO

El POST se hace dentro de la petición, antes de responder al panel,
porque Vercel congela la función al responder y un envío «en segundo
plano» no se ejecutaría. Tope de 4 s por paso: si el gateway no
contesta, la orden queda en cola con aviso='fallido' y el panel lo dice.

`urllib` y `http.client`, sin dependencias: una llamada no justifica
una biblioteca en el bundle.
"""
from __future__ import annotations

import hashlib
import hmac
import http.client
import json
import logging
import os
import socket
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request

logger = logging.getLogger("agw-cloud-api.webhook")

_TIMEOUT_S = 4.0
_DOH = (
    "https://dns.google/resolve?name={host}&type=A",
    "https://cloudflare-dns.com/dns-query?name={host}&type=A",
)
# host -> (ips, expira). Vive lo que viva la instancia de la función.
_cache_ip: dict[str, tuple[list[str], float]] = {}
_CACHE_S = 600


def firmar(secreto: str, timestamp: str, cuerpo: bytes) -> str:
    return hmac.new(secreto.encode(), f"{timestamp}.".encode() + cuerpo, hashlib.sha256).hexdigest()


def _resolver_doh(host: str) -> list[str]:
    ahora = time.monotonic()
    en_cache = _cache_ip.get(host)
    if en_cache and en_cache[1] > ahora:
        return en_cache[0]
    for plantilla in _DOH:
        try:
            req = urllib.request.Request(plantilla.format(host=host),
                                         headers={"accept": "application/dns-json"})
            with urllib.request.urlopen(req, timeout=_TIMEOUT_S) as r:
                data = json.load(r)
            ips = [a["data"] for a in data.get("Answer", []) if a.get("type") == 1]
            if ips:
                _cache_ip[host] = (ips, ahora + _CACHE_S)
                return ips
        except Exception as exc:                      # noqa: BLE001
            logger.debug("DoH %s falló: %s", plantilla.split("/")[2], exc)
    return []


class _HTTPSPorIP(http.client.HTTPSConnection):
    """HTTPS contra una IP, presentando el nombre real en SNI y en el certificado."""

    def __init__(self, ip: str, nombre: str, timeout: float):
        super().__init__(ip, 443, timeout=timeout, context=ssl.create_default_context())
        self._nombre = nombre

    def connect(self) -> None:
        sock = socket.create_connection((self.host, self.port), self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self._nombre)


def _post(url: str, cuerpo: bytes, cabeceras: dict) -> int:
    """Devuelve el código HTTP. Resolución normal primero; DoH + IP si no hay DNS."""
    partes = urllib.parse.urlsplit(url)
    host = partes.hostname or ""
    try:
        req = urllib.request.Request(url, data=cuerpo, method="POST", headers=cabeceras)
        with urllib.request.urlopen(req, timeout=_TIMEOUT_S) as r:
            return r.status
    except urllib.error.HTTPError as exc:
        return exc.code
    except (urllib.error.URLError, OSError) as exc:
        # Solo se toma el desvío si lo que falló fue resolver el nombre.
        razon = getattr(exc, "reason", exc)
        if not isinstance(razon, (socket.gaierror, OSError)) or partes.scheme != "https":
            raise
        logger.info("DNS del runtime no resuelve %s (%s); resolviendo por DoH", host, razon)

    ips = _resolver_doh(host)
    if not ips:
        raise OSError(f"sin DNS para {host}, ni por DoH")
    ultimo: Exception | None = None
    for ip in ips[:2]:
        con = _HTTPSPorIP(ip, host, _TIMEOUT_S)
        try:
            con.request("POST", partes.path or "/", body=cuerpo, headers={**cabeceras, "Host": host})
            return con.getresponse().status
        except Exception as exc:                      # noqa: BLE001
            ultimo = exc
        finally:
            con.close()
    raise OSError(f"ninguna IP de {host} respondió: {ultimo}")


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
    cabeceras = {
        "Content-Type": "application/json",
        "Content-Length": str(len(cuerpo)),
        "X-AGW-Timestamp": ts,
        "X-AGW-Signature": firmar(secreto, ts, cuerpo),
        "User-Agent": "agw-cloud-api/webhook",
    }
    t0 = time.monotonic()
    try:
        codigo = _post(url.rstrip("/") + "/webhook/ordenes", cuerpo, cabeceras)
        ok = 200 <= codigo < 300
        logger.info("Aviso al gateway %s: %s en %.0f ms", gateway_id,
                    "ok" if ok else f"HTTP {codigo}", (time.monotonic() - t0) * 1000)
        return "entregado" if ok else "fallido"
    except Exception as exc:                          # noqa: BLE001
        logger.warning("Aviso al gateway %s fallido tras %.0f ms: %s", gateway_id,
                       (time.monotonic() - t0) * 1000, exc)
        return "fallido"
