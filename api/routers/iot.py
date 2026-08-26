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
