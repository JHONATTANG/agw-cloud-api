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
