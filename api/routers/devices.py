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
class DeviceAssignmentPayload(BaseModel):
    node_id: str = Field(..., min_length=3, max_length=100, description="ID del nodo Fog/Gateway o ESP32 (ej. FOG_RPI_01)")
    alias: str = Field(..., min_length=2, max_length=255, description="Nombre amigable, ej. 'Cultivo Hierbabuena A'")

class DeviceAssignmentResponse(BaseModel):
    id: int
    user_id: str
    node_id: str
    alias: Optional[str]
    assigned_at: str

class DeviceAliasUpdate(BaseModel):
    alias: str = Field(..., min_length=2, max_length=255)

# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@devices_router.post(
    "/assign",
    status_code=status.HTTP_201_CREATED,
    summary="Asigna un nodo existente al usuario",
    response_description="Confirmación de asignación",
)
async def assign_device(
    payload: DeviceAssignmentPayload,
    current_user: dict = Depends(get_current_user)
):
    """
    Asigna un nodo/dispositivo IoT (node_id) al usuario actual con un alias.
    """
    conn = get_db_connection()
    cur = conn.cursor()

    try:
        cur.execute(
            """
            INSERT INTO public.device_assignments (user_id, node_id, alias)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id, node_id) DO UPDATE SET alias = EXCLUDED.alias
            RETURNING id, user_id, node_id, alias, assigned_at
            """,
            (current_user["id"], payload.node_id, payload.alias)
        )
        row = cur.fetchone()
        conn.commit()
    except Exception as exc:
        conn.rollback()
        logger.error(f"Error asignando dispositivo: {exc}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error asignando el dispositivo.")
    finally:
        cur.close()
        conn.close()

    return {
        "id": row["id"],
        "user_id": str(row["user_id"]),
        "node_id": row["node_id"],
        "alias": row["alias"],
        "assigned_at": row["assigned_at"].isoformat() if row["assigned_at"] else None
    }

@devices_router.get(
    "",
    status_code=status.HTTP_200_OK,
    summary="Lista dispositivos asignados al usuario",
    response_description="Lista de dispositivos asignados",
)
async def list_devices(current_user: dict = Depends(get_current_user)):
    """
    Retorna todos los dispositivos asignados al usuario actual.
    """
    conn = get_db_connection()
    cur = conn.cursor()

    try:
        cur.execute(
            """
            SELECT id, user_id, node_id, alias, assigned_at 
            FROM public.device_assignments 
            WHERE user_id = %s
            ORDER BY assigned_at DESC
            """,
            (current_user["id"],)
        )
        rows = cur.fetchall()
    except Exception as exc:
        logger.error(f"Error listando dispositivos: {exc}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error consultando dispositivos.")
    finally:
        cur.close()
        conn.close()

    results = []
    for row in rows:
        results.append({
            "id": row["id"],
            "user_id": str(row["user_id"]),
            "node_id": row["node_id"],
            "alias": row["alias"],
            "assigned_at": row["assigned_at"].isoformat() if row["assigned_at"] else None
        })

    return results

@devices_router.put(
    "/{assignment_id}",
    status_code=status.HTTP_200_OK,
    summary="Actualiza el alias de una asignación",
    response_description="Dispositivo actualizado",
)
async def update_device_alias(
    assignment_id: int,
    payload: DeviceAliasUpdate,
    current_user: dict = Depends(get_current_user)
):
    """
    Actualiza el alias (`alias`) para una asignación específica mediante su `assignment_id`.
    Verifica que la asignación pertenezca al usuario JWT actual.   
    """
    conn = get_db_connection()
    cur = conn.cursor()

    try:
        cur.execute(
            """
            UPDATE public.device_assignments
            SET alias = %s
            WHERE id = %s AND user_id = %s
            RETURNING id, user_id, node_id, alias, assigned_at
            """,
            (payload.alias, assignment_id, current_user["id"])
        )
        row = cur.fetchone()
        conn.commit()
    except Exception as exc:
        conn.rollback()
        logger.error(f"Error actualizando alias de dispositivo: {exc}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error actualizando dispositivo.")
    finally:
        cur.close()
        conn.close()

    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asignación de dispositivo no encontrada o no te pertenece.")

    return {
        "id": row["id"],
        "user_id": str(row["user_id"]),
        "node_id": row["node_id"],
        "alias": row["alias"],
        "assigned_at": row["assigned_at"].isoformat() if row["assigned_at"] else None
    }

@devices_router.delete(
    "/{assignment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remueve una asignación de dispositivo",
    response_description="No Content",
)
async def delete_device_assignment(
    assignment_id: int,
    current_user: dict = Depends(get_current_user)
):
    """
    Remueve el dispositivo del usuario (`DELETE` en `device_assignments`).
    """
    conn = get_db_connection()
    cur = conn.cursor()

    try:
        cur.execute(
            "DELETE FROM public.device_assignments WHERE id = %s AND user_id = %s RETURNING id",
            (assignment_id, current_user["id"])
        )
        row = cur.fetchone()
        conn.commit()
    except Exception as exc:
        conn.rollback()
        logger.error(f"Error eliminando asignación: {exc}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error eliminando dispositivo.")
    finally:
        cur.close()
        conn.close()

    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asignación de dispositivo no encontrada o no te pertenece.")

    # 204 No Content se maneja directo devolviendo None
    return None
