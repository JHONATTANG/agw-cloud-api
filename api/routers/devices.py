import logging
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, status, HTTPException
from pydantic import BaseModel, Field

# Importar configuración y dependencias de seguridad
from api.security import get_current_user, get_db_connection

logger = logging.getLogger("agw-cloud-api.devices")

devices_router = APIRouter(prefix="/api/devices", tags=["Devices"])

# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class GatewayPayload(BaseModel):
    gateway_id: str = Field(..., min_length=3, max_length=100, description="ID del Broker/Gateway (ej. FOG_RPI_01)")
    alias: str = Field(..., min_length=2, max_length=255, description="Alias del Broker")

class GatewayUpdate(BaseModel):
    alias: str = Field(..., min_length=2, max_length=255)

class EdgeNodePayload(BaseModel):
    sensor_id: str = Field(..., min_length=3, max_length=100, description="ID del ESP32 (ej. ESP32_TIERRA_01)")
    node_type: str = Field(..., description="TIERRA o HIDROPONIA")
    alias: str = Field(..., min_length=2, max_length=255, description="Alias del nodo")

class EdgeNodeUpdate(BaseModel):
    node_type: str
    alias: str

# ---------------------------------------------------------------------------
# Endpoints - Gateways (Brokers)
# ---------------------------------------------------------------------------

@devices_router.post(
    "/gateways",
    status_code=status.HTTP_201_CREATED,
    summary="Asigna un Broker ESP32/Raspberry al usuario",
)
async def assign_gateway(payload: GatewayPayload, current_user: dict = Depends(get_current_user)):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO public.gateways (user_id, gateway_id, alias)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id, gateway_id) DO UPDATE SET alias = EXCLUDED.alias
            RETURNING id, user_id, gateway_id, alias, created_at
            """,
            (current_user["id"], payload.gateway_id, payload.alias)
        )
        row = cur.fetchone()
        conn.commit()
    except Exception as exc:
        conn.rollback()
        logger.error(f"Error asignando gateway: {exc}")
        raise HTTPException(status_code=500, detail="Error asignando el gateway.")
    finally:
        cur.close()
        conn.close()

    return dict(row)

@devices_router.get(
    "/gateways",
    status_code=status.HTTP_200_OK,
    summary="Lista brokers asignados al usuario",
)
async def list_gateways(current_user: dict = Depends(get_current_user)):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT id, user_id, gateway_id, alias, created_at 
            FROM public.gateways 
            WHERE user_id = %s
            ORDER BY created_at DESC
            """,
            (current_user["id"],)
        )
        rows = cur.fetchall()
    finally:
        cur.close()
        conn.close()
    return [dict(r) for r in rows]

@devices_router.put(
    "/gateways/{gateway_uuid}",
    status_code=status.HTTP_200_OK,
    summary="Actualiza el alias de un broker"
)
async def update_gateway(gateway_uuid: str, payload: GatewayUpdate, current_user: dict = Depends(get_current_user)):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            UPDATE public.gateways
            SET alias = %s
            WHERE id = %s AND user_id = %s
            RETURNING id, user_id, gateway_id, alias, created_at
            """,
            (payload.alias, gateway_uuid, current_user["id"])
        )
        row = cur.fetchone()
        conn.commit()
    except Exception as exc:
        conn.rollback()
        raise HTTPException(status_code=500, detail="Error actualizando gateway.")
    finally:
        cur.close()
        conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="Gateway no encontrado.")
    return dict(row)

@devices_router.delete(
    "/gateways/{gateway_uuid}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remueve un broker"
)
async def delete_gateway(gateway_uuid: str, current_user: dict = Depends(get_current_user)):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "DELETE FROM public.gateways WHERE id = %s AND user_id = %s RETURNING id",
            (gateway_uuid, current_user["id"])
        )
        row = cur.fetchone()
        conn.commit()
    finally:
        cur.close()
        conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="Gateway no encontrado.")
    return None

# ---------------------------------------------------------------------------
# Endpoints - Edge Nodes (ESP32)
# ---------------------------------------------------------------------------

@devices_router.post(
    "/gateways/{gateway_uuid}/nodes",
    status_code=status.HTTP_201_CREATED,
    summary="Asigna un nodo ESP32 a un broker",
)
async def assign_node(gateway_uuid: str, payload: EdgeNodePayload, current_user: dict = Depends(get_current_user)):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # Validar que el gateway pertenece al usuario
        cur.execute("SELECT id FROM public.gateways WHERE id = %s AND user_id = %s", (gateway_uuid, current_user["id"]))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Gateway no encontrado o no te pertenece.")

        cur.execute(
            """
            INSERT INTO public.edge_nodes (gateway_id, sensor_id, node_type, alias)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (gateway_id, sensor_id) DO UPDATE SET alias = EXCLUDED.alias, node_type = EXCLUDED.node_type
            RETURNING id, gateway_id, sensor_id, node_type, alias, created_at
            """,
            (gateway_uuid, payload.sensor_id, payload.node_type, payload.alias)
        )
        row = cur.fetchone()
        conn.commit()
    except HTTPException:
        raise
    except Exception as exc:
        conn.rollback()
        logger.error(f"Error asignando nodo: {exc}")
        raise HTTPException(status_code=500, detail="Error asignando el nodo.")
    finally:
        cur.close()
        conn.close()

    return dict(row)

@devices_router.get(
    "/gateways/{gateway_uuid}/nodes",
    status_code=status.HTTP_200_OK,
    summary="Lista los nodos ESP32 de un broker",
)
async def list_nodes(gateway_uuid: str, current_user: dict = Depends(get_current_user)):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # Validar que el gateway pertenece al usuario
        cur.execute("SELECT id FROM public.gateways WHERE id = %s AND user_id = %s", (gateway_uuid, current_user["id"]))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Gateway no encontrado o no te pertenece.")

        cur.execute(
            "SELECT id, gateway_id, sensor_id, node_type, alias, created_at FROM public.edge_nodes WHERE gateway_id = %s",
            (gateway_uuid,)
        )
        rows = cur.fetchall()
    finally:
        cur.close()
        conn.close()

    return [dict(r) for r in rows]

@devices_router.put(
    "/nodes/{node_uuid}",
    status_code=status.HTTP_200_OK,
    summary="Actualiza configuracion de un nodo"
)
async def update_node(node_uuid: str, payload: EdgeNodeUpdate, current_user: dict = Depends(get_current_user)):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # Validar que el gateway de este nodo pertenece al usuario
        cur.execute(
            """
            SELECT e.id FROM public.edge_nodes e
            JOIN public.gateways g ON e.gateway_id = g.id
            WHERE e.id = %s AND g.user_id = %s
            """,
            (node_uuid, current_user["id"])
        )
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Nodo no encontrado.")

        cur.execute(
            """
            UPDATE public.edge_nodes
            SET alias = %s, node_type = %s
            WHERE id = %s
            RETURNING id, gateway_id, sensor_id, node_type, alias, created_at
            """,
            (payload.alias, payload.node_type, node_uuid)
        )
        row = cur.fetchone()
        conn.commit()
    except HTTPException:
        raise
    except Exception as exc:
        conn.rollback()
        raise HTTPException(status_code=500, detail="Error actualizando nodo.")
    finally:
        cur.close()
        conn.close()

    return dict(row)

@devices_router.delete(
    "/nodes/{node_uuid}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remueve un nodo ESP32"
)
async def delete_node(node_uuid: str, current_user: dict = Depends(get_current_user)):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            DELETE FROM public.edge_nodes e
            USING public.gateways g
            WHERE e.gateway_id = g.id AND e.id = %s AND g.user_id = %s
            RETURNING e.id
            """,
            (node_uuid, current_user["id"])
        )
        row = cur.fetchone()
        conn.commit()
    finally:
        cur.close()
        conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="Nodo no encontrado.")
    return None


# ---------------------------------------------------------------------------
# Inventario agregado
# ---------------------------------------------------------------------------
#
# POR QUÉ EXISTE ESTE ENDPOINT
#
# El dashboard y la página de dispositivos pedían GET /api/devices y
# recibían un 404: solo existían /gateways y /gateways/{uuid}/nodes. Por
# eso ambas pantallas salían vacías aunque la tabla tuviera el gateway y
# el nodo dados de alta desde el primer día.
#
# Podría haberse resuelto en el navegador encadenando las dos llamadas,
# pero el estado que de verdad importa —si el aparato está vivo— no está
# en esas tablas: está en la telemetría. Resolverlo aquí evita además una
# cascada de peticiones por cada gateway.
#
# El estado se deduce del silencio, no de una columna: un nodo no avisa
# de que se murió. El umbral es tres veces la cadencia de publicación
# (300 s), suficiente para no marcar una caída por perder una trama.

_SILENCIO_ALERTA_S = 900      # 3 cadencias perdidas -> ERROR
_SILENCIO_CAIDA_S = 3600      # una hora sin hablar  -> OFFLINE


@devices_router.get(
    "",
    summary="Inventario completo con el estado deducido de la telemetría",
)
async def inventario(current_user: dict = Depends(get_current_user)):
    """
    Devuelve gateways y nodos en una sola lista plana, que es como los
    pinta la interfaz. El gateway hereda el estado del nodo más reciente
    que cuelga de él: si sus nodos publican, el gateway está enrutando.
    """
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            WITH ultima AS (
                -- DISTINCT ON es la forma barata en Postgres de coger la
                -- última fila por sensor: usa el índice y no ordena todo.
                SELECT DISTINCT ON (sensor_id)
                       sensor_id, t_rx, fw, rssi, temperatura,
                       humedad_ambiente, ec, agua, uptime_ms
                FROM public.telemetria_indoor
                ORDER BY sensor_id, t_rx DESC
            )
            SELECT n.id, n.sensor_id, n.node_type, n.alias, n.created_at,
                   g.gateway_id, g.alias AS gateway_alias,
                   u.t_rx, u.fw, u.rssi, u.temperatura,
                   u.humedad_ambiente, u.ec, u.agua, u.uptime_ms,
                   EXTRACT(EPOCH FROM (now() - u.t_rx)) AS silencio_s
            FROM public.edge_nodes n
            JOIN public.gateways g ON g.id = n.gateway_id
            LEFT JOIN ultima u ON u.sensor_id = n.sensor_id
            WHERE g.user_id = %s
            ORDER BY n.created_at
            """,
            (current_user["id"],),
        )
        nodos = [dict(r) for r in cur.fetchall()]

        cur.execute(
            """
            SELECT id, gateway_id, alias, created_at
            FROM public.gateways WHERE user_id = %s ORDER BY created_at
            """,
            (current_user["id"],),
        )
        gws = [dict(r) for r in cur.fetchall()]
    finally:
        cur.close()
        conn.close()

    def _estado(silencio) -> str:
        if silencio is None:
            return "MAINTENANCE"        # dado de alta pero nunca publicó
        if silencio > _SILENCIO_CAIDA_S:
            return "OFFLINE"
        if silencio > _SILENCIO_ALERTA_S:
            return "ERROR"
        return "ONLINE"

    salida: List[dict] = []

    # Silencio mínimo entre los nodos de cada gateway: el gateway está tan
    # vivo como su nodo más despierto.
    silencio_por_gw: dict = {}
    for n in nodos:
        s = n["silencio_s"]
        if s is None:
            continue
        gid = n["gateway_id"]
        silencio_por_gw[gid] = min(silencio_por_gw.get(gid, s), float(s))

    for g in gws:
        sil = silencio_por_gw.get(g["gateway_id"])
        salida.append({
            "id": str(g["id"]),
            "device_uid": g["gateway_id"],
            "device_type": "GATEWAY",
            "status": _estado(sil),
            "last_seen": None,
            "alias": g["alias"],
            "location": "Cultivo indoor · hierbabuena",
            "description": "Nodo fog: broker MQTT, motor de reglas y buffer local",
            "gateway_id": g["gateway_id"],
            "created_at": g["created_at"].isoformat() if g["created_at"] else None,
            "silencio_s": sil,
        })

    for n in nodos:
        sil = float(n["silencio_s"]) if n["silencio_s"] is not None else None
        salida.append({
            "id": str(n["id"]),
            "device_uid": n["sensor_id"],
            "sensor_id": n["sensor_id"],
            "device_type": n["node_type"],
            "status": _estado(sil),
            "last_seen": n["t_rx"].isoformat() if n["t_rx"] else None,
            "alias": n["alias"],
            "location": "Cultivo indoor · hierbabuena",
            "description": "Nodo ESP32: sensores, relés y ciclos de riego",
            "firmware_version": n["fw"],
            "gateway_id": n["gateway_id"],
            "created_at": n["created_at"].isoformat() if n["created_at"] else None,
            "silencio_s": sil,
            # La última lectura viaja con el inventario para que las
            # tarjetas muestren algo sin una segunda petición por nodo.
            "ultima_lectura": {
                "temperatura": float(n["temperatura"]) if n["temperatura"] is not None else None,
                "humedad": float(n["humedad_ambiente"]) if n["humedad_ambiente"] is not None else None,
                "ec": float(n["ec"]) if n["ec"] is not None else None,
                "rssi": n["rssi"],
                "agua": n["agua"],
                "uptime_ms": n["uptime_ms"],
            },
        })

    return salida
