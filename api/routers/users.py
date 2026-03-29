import logging
from fastapi import APIRouter, Depends, status, HTTPException
from pydantic import BaseModel, Field

# Importar configuración y dependencias de seguridad
from api.security import get_current_user, get_db_connection

logger = logging.getLogger("agw-cloud-api.users")

users_router = APIRouter(prefix="/api/users", tags=["Users"])

# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class UserProfileResponse(BaseModel):
    id: str
    email: str
    full_name: str | None
    created_at: str

class UserProfileUpdate(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=100)

# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@users_router.get(
    "/me",
    status_code=status.HTTP_200_OK,
    summary="Obtener perfil del usuario actual",
    response_description="Datos de perfil",
)
async def get_me(current_user: dict = Depends(get_current_user)):
    """
    Retorna los datos del usuario autenticado (extraído del JWT).
    """
    # Serializar la fecha
    return {
        "id": str(current_user["id"]),
        "email": current_user["email"],
        "full_name": current_user["full_name"],
        "created_at": current_user["created_at"].isoformat() if current_user["created_at"] else None
    }

@users_router.put(
    "/me",
    status_code=status.HTTP_200_OK,
    summary="Actualizar perfil del usuario actual",
    response_description="Datos actualizados",
)
async def update_me(payload: UserProfileUpdate, current_user: dict = Depends(get_current_user)):
    """
    Actualiza el perfil (nombre) del usuario autenticado.
    """
    conn = get_db_connection()
    cur = conn.cursor()

    try:
        cur.execute(
            """
            UPDATE public.users 
            SET full_name = %s 
            WHERE id = %s 
            RETURNING id, email, full_name, created_at
            """,
            (payload.full_name, current_user["id"])
        )
        updated_user = cur.fetchone()
        conn.commit()
    except Exception as exc:
        conn.rollback()
        logger.error(f"Error actualizando usuario: {exc}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error actualizando el perfil.")
    finally:
        cur.close()
        conn.close()

    if not updated_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado en la actualización.")

    return {
        "id": str(updated_user["id"]),
        "email": updated_user["email"],
        "full_name": updated_user["full_name"],
        "created_at": updated_user["created_at"].isoformat() if updated_user["created_at"] else None
    }
