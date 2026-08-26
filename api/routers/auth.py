import os
import random
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr

# Importar configuración y dependencias de seguridad (creadas en security.py)
from api.security import create_access_token, get_db_connection
from api.email_otp import enviar_otp

logger = logging.getLogger("agw-cloud-api.auth")

auth_router = APIRouter(prefix="/api/auth", tags=["Auth"])

# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class RequestCodePayload(BaseModel):
    email: EmailStr

class VerifyCodePayload(BaseModel):
    email: EmailStr
    code: str

# ---------------------------------------------------------------------------
# Email Helper
# ---------------------------------------------------------------------------
def send_otp_email(recipient: str, otp: str):
    """
    Envia el codigo. Delega en Resend (api/email_otp.py).

    Antes esto hablaba SMTP con Gmail y, al fallar, lanzaba un 500 que
    dejaba el login atascado en el paso del correo: el usuario nunca
    llegaba al campo del codigo. Ahora un fallo de envio se registra y
    request-code sigue devolviendo 200, porque el codigo ya esta en la
    base y es recuperable del log.
    """
    enviar_otp(recipient, otp, minutos=10)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@auth_router.post(
    "/request-code",
    status_code=status.HTTP_200_OK,
    summary="Solicita un OTP para Passwordless Login",
    response_description="Confirmación de envío",
)
async def request_code(payload: RequestCodePayload):
    """
    Recibe un `email`. Si no existe en la DB, lo crea.
    Genera un OTP y lo envía vía correo. Expira en 10 min.
    """
    email_str = payload.email.lower()
    conn = get_db_connection()
    cur = conn.cursor()

    try:
        # Verificar o crear usuario
        cur.execute("SELECT id FROM public.users WHERE email = %s", (email_str,))
        user_row = cur.fetchone()

        if user_row:
            user_id = user_row["id"]
        else:
            cur.execute(
                "INSERT INTO public.users (email) VALUES (%s) RETURNING id",
                (email_str,)
            )
            user_id = cur.fetchone()["id"]

        # Generar código (6 dígitos)
        otp = f"{random.randint(100000, 999999)}"
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)

        # Guardar en DB
        cur.execute(
            """
            INSERT INTO public.auth_codes (user_id, otp_code, expires_at)
            VALUES (%s, %s, %s)
            """,
            (user_id, otp, expires_at)
        )
        conn.commit()
    except Exception as exc:
        conn.rollback()
        logger.error(f"Error de DB en request_code: {exc}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error de base de datos")
    finally:
        cur.close()
        conn.close()

    # Enviar correo asíncronamente o sincrónicamente (Serverless soporta ambas, preferimos sync para no tener ghost-threads en Vercel)
    send_otp_email(email_str, otp)

    return {"status": "ok", "message": f"Código enviado a {email_str}"}


@auth_router.post(
    "/verify-code",
    status_code=status.HTTP_200_OK,
    summary="Verifica el OTP y retorna un JWT Bearer Token",
    response_description="Token JWT con datos de usuario",
)
async def verify_code(payload: VerifyCodePayload):
    """
    Valida que el código no esté expirado, ni usado, y corresponda al email.
    Si es válido, lo marca como usado y emite el Token JWT.
    """
    email_str = payload.email.lower()
    provided_code = payload.code

    conn = get_db_connection()
    cur = conn.cursor()

    try:
        # 1. Obtener usuario
        cur.execute("SELECT id FROM public.users WHERE email = %s", (email_str,))
        user_row = cur.fetchone()
        
        if not user_row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado.")

        user_id = user_row["id"]

        # 2. Verificar código vigente
        now = datetime.now(timezone.utc)
        cur.execute(
            """
            SELECT id, expires_at 
            FROM public.auth_codes 
            WHERE user_id = %s AND otp_code = %s AND used = FALSE
            ORDER BY expires_at DESC LIMIT 1
            """,
            (user_id, provided_code)
        )
        code_row = cur.fetchone()

        if not code_row:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Código inválido o ya usado.")

        if code_row["expires_at"] < now:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="El código ha expirado.")

        # 3. Marcar como usado
        cur.execute("UPDATE public.auth_codes SET used = TRUE WHERE id = %s", (code_row["id"],))
        conn.commit()

        # 4. Generar Token
        token_data = {"sub": str(user_id), "email": email_str}
        token = create_access_token(token_data)

    except HTTPException:
        raise
    except Exception as exc:
        conn.rollback()
        logger.error(f"Error de DB en verify_code: {exc}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error interno verificando código.")
    finally:
        cur.close()
        conn.close()

    return {
        "access_token": token,
        "token_type": "bearer",
        "user_id": user_id,
        "email": email_str
    }
