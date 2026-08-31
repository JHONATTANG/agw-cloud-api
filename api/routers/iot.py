"""
Alertas y comandos — los dos endpoints que el dashboard lleva llamando
desde que se construyó y que nunca existieron en el backend.

`useAlerts.ts` pide `/api/iot/alerts` y `useCommands.ts` pide
`/api/iot/commands`. Ambos devolvían 404, así que esas dos páginas del
dashboard estaban rotas por diseño, no por configuración.

SOBRE LOS COMANDOS

El anteproyecto compromete "recibir órdenes revisando una tabla de
órdenes" (deuda 7.10). Aquí está esa tabla: el dashboard encola, y la
Raspberry consulta y marca. La nube NO habla directamente con el ESP32
—no puede, está detrás del NAT del gateway— así que el mando es
asíncrono por diseño y el estado de cada orden es observable.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from api.security import get_current_user, get_db_connection, require_iot_token

logger = logging.getLogger("agw-cloud-api.iot")

iot_router = APIRouter(prefix="/api/iot", tags=["IoT"])


class ComandoPayload(BaseModel):
    sensor_id: str = Field(..., min_length=3, max_length=100)
    # El JSON que entiende el firmware, tal cual. No se traduce aquí:
    # el contrato canónico es el del firmware (MCD §6.5), y una capa de
    # traducción intermedia sería un sitio más donde desincronizarse.
    comando: dict = Field(..., description='p.ej. {"cmd":"luz","encendida":false}')
    nota: Optional[str] = Field(None, max_length=255)


def _filas(sql: str, params: tuple = ()) -> list[dict]:
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(sql, params)
        return [dict(r) for r in cur.fetchall()] if cur.description else []
    finally:
        cur.close()
        conn.close()


def _ejecutar(sql: str, params: tuple = ()) -> dict:
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(sql, params)
        fila = dict(cur.fetchone()) if cur.description else {}
        conn.commit()
        return fila
    except Exception as exc:
        conn.rollback()
        logger.error("Fallo la escritura: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error de base de datos",
        )
    finally:
        cur.close()
        conn.close()


# ── Alertas ───────────────────────────────────────────────────

@iot_router.get("/alerts", summary="Alertas generadas por el motor de reglas del fog")
async def alertas(
    dias: int = Query(7, ge=1, le=90),
    limite: int = Query(100, ge=1, le=1000),
    _user: dict = Depends(get_current_user),
):
    """
    Las alertas las genera el gateway, no la nube: el motor de reglas
    corre en la Raspberry para que siga funcionando sin internet. Aquí
    solo se consultan las que llegaron.
    """
    return {
        "resumen": _filas("""
            SELECT evento AS tipo, COUNT(*) AS n, MAX(ts) AS ultimo
            FROM node_eventos
            WHERE ts > now() - (%s || ' days')::interval
              AND evento NOT LIKE 'riego_%%'
            GROUP BY 1 ORDER BY n DESC
        """, (dias,)),
        "alertas": _filas("""
            SELECT ts, sensor_id, evento AS tipo, detalle
            FROM node_eventos
            WHERE ts > now() - (%s || ' days')::interval
              AND evento NOT LIKE 'riego_%%'
            ORDER BY ts DESC LIMIT %s
        """, (dias, limite)),
    }


# ── Comandos ──────────────────────────────────────────────────

@iot_router.get("/commands", summary="Historial de ordenes enviadas al nodo")
async def listar_comandos(
    limite: int = Query(50, ge=1, le=500),
    _user: dict = Depends(get_current_user),
):
    return {
        "comandos": _filas("""
            SELECT id, creado_en, sensor_id, comando, estado,
                   entregado_en, resultado, nota
            FROM public.comandos
            ORDER BY creado_en DESC LIMIT %s
        """, (limite,)),
    }


@iot_router.post(
    "/commands",
    status_code=status.HTTP_201_CREATED,
    summary="Encola una orden para el nodo",
)
async def crear_comando(
    payload: ComandoPayload,
    user: dict = Depends(get_current_user),
):
    fila = _ejecutar("""
        INSERT INTO public.comandos (sensor_id, comando, nota, creado_por)
        VALUES (%s, %s, %s, %s)
        RETURNING id, creado_en, sensor_id, comando, estado
    """, (payload.sensor_id, json.dumps(payload.comando),
          payload.nota, user.get("email")))
    logger.info("Comando encolado: %s -> %s", payload.sensor_id, payload.comando)
    return fila


@iot_router.get(
    "/commands/pending",
    summary="Ordenes sin entregar — la consulta el gateway, no el navegador",
)
async def pendientes(
    limite: int = Query(20, ge=1, le=100),
    _token: str = Depends(require_iot_token),
):
    """
    Protegido con el Bearer estático del Fog Node, no con el JWT de
    usuario: quien llama aquí es la Raspberry, que no tiene sesión.
    """
    return {
        "comandos": _filas("""
            SELECT id, sensor_id, comando, creado_en
            FROM public.comandos
            WHERE estado = 'pendiente'
            ORDER BY creado_en ASC LIMIT %s
        """, (limite,)),
    }


@iot_router.post(
    "/commands/{comando_id}/ack",
    summary="El gateway confirma que entrego la orden",
)
async def confirmar(
    comando_id: int,
    resultado: Optional[str] = None,
    _token: str = Depends(require_iot_token),
):
    """
    Sin este acuse, una orden encolada y otra entregada son
    indistinguibles, y el operador no sabría si el nodo la recibió.
    """
    fila = _ejecutar("""
        UPDATE public.comandos
        SET estado = 'entregado', entregado_en = now(), resultado = %s
        WHERE id = %s AND estado = 'pendiente'
        RETURNING id, estado, entregado_en
    """, (resultado, comando_id))

    if not fila:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="La orden no existe o ya estaba entregada",
        )
    return fila


# ── Eventos del nodo ──────────────────────────────────────────
#
#  POR QUÉ HACÍA FALTA ESTA RUTA
#
#  El gateway registraba cada decisión del borde —inicio y fin de cada
#  ciclo de riego, caídas, reconexiones, correcciones de programa— en su
#  SQLite local, y ahí se quedaban. El edge solo llamaba a /telemetria,
#  /health y /commands/pending: no existía ninguna puerta por la que un
#  evento pudiera entrar.
#
#  Los eventos que había en la nube entraron por una carga manual y se
#  congelaron el 26/08. Cualquier análisis apoyado en ellos —los ciclos
#  de riego por hora del panel, las decisiones del borde de la página
#  fog— mostraba cifras de hace días como si fueran de ahora, que es
#  peor que no mostrarlas.
#
#  IDEMPOTENTE POR CONSTRUCCIÓN
#
#  La tabla ya traía UNIQUE (sensor_id, ts, evento) de la migración que
#  la creó. Se aprovecha: el gateway puede reenviar lo que quiera y los
#  repetidos se descartan en el servidor. Eso permite que el remitente
#  del borde marque como enviado sin miedo, y que una subida a medias se
#  reintente entera sin duplicar nada.


class EventoEntrada(BaseModel):
    """Un evento tal como lo registró el gateway."""

    ts: datetime = Field(..., description="Instante del evento, con zona")
    sensor_id: str = Field(..., min_length=3, max_length=100)
    evento: str = Field(..., min_length=2, max_length=80)
    detalle: Optional[dict] = None


class LoteEventos(BaseModel):
    """
    Los eventos van en lote y no de uno en uno.

    Un ciclo de riego produce dos eventos y el gateway puede acumular
    cientos tras un corte largo. Con una petición por evento, recuperar
    un día de desconexión serían cientos de invocaciones sin servidor,
    cada una con su arranque en frío.
    """

    gateway_id: str = Field(..., min_length=3, max_length=100)
    eventos: list[EventoEntrada] = Field(..., min_length=1, max_length=500)


@iot_router.post(
    "/eventos",
    status_code=status.HTTP_201_CREATED,
    summary="El gateway sube los eventos que registro en el borde",
)
async def ingerir_eventos(
    lote: LoteEventos,
    _token: str = Depends(require_iot_token),
):
    """
    Devuelve cuántos entraron y cuántos ya estaban.

    Distinguirlos importa para el remitente: si todo sale como
    `duplicado` sabe que ya había subido ese tramo y puede marcarlo sin
    volver a intentarlo, en vez de reenviarlo en cada vuelta.
    """
    conn = get_db_connection()
    cur = conn.cursor()
    insertados = 0
    try:
        for e in lote.eventos:
            cur.execute(
                """
                INSERT INTO public.node_eventos
                       (ts, gateway_id, sensor_id, evento, detalle)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (sensor_id, ts, evento) DO NOTHING
                RETURNING id
                """,
                (e.ts, lote.gateway_id, e.sensor_id, e.evento,
                 json.dumps(e.detalle) if e.detalle is not None else None),
            )
            if cur.fetchone() is not None:
                insertados += 1
        conn.commit()
    except Exception as exc:                                   # noqa: BLE001
        conn.rollback()
        logger.error("Fallo la ingesta de eventos: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error guardando los eventos",
        )
    finally:
        cur.close()
        conn.close()

    recibidos = len(lote.eventos)
    logger.info("Eventos: %s recibidos, %s nuevos", recibidos, insertados)
    return {
        "recibidos": recibidos,
        "insertados": insertados,
        "duplicados": recibidos - insertados,
    }
