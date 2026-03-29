import os
import random
import logging
import smtplib
from email.message import EmailMessage
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr

# Importar configuración y dependencias de seguridad (creadas en security.py)
from api.security import create_access_token, get_db_connection

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
    smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USERNAME")
    smtp_pass = os.getenv("SMTP_PASSWORD")

    if not smtp_user or not smtp_pass:
        logger.error("Credenciales SMTP no configuradas. Simulando envío.")
        logger.info(f"SIMULADO: Enviado OTP {otp} a {recipient}")
        return

    msg = EmailMessage()
    msg["Subject"] = "Tu código de acceso - Noxum Soluciones AGW"
    msg["From"] = f"Noxum Soluciones <{smtp_user}>"
    msg["To"] = recipient

    # HTML Body Profesional
    html_content = f"""
    <html>
    <body style="font-family: Arial, sans-serif; background-color: #f4f6f8; margin: 0; padding: 20px;">
        <div style="max-width: 500px; margin: 0 auto; background-color: #ffffff; border-radius: 8px; padding: 30px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
            <header style="border-bottom: 2px solid #10b981; padding-bottom: 20px; text-align: center;">
                <h1 style="color: #047857; margin: 0;">Noxum Soluciones</h1>
                <p style="color: #6b7280; font-size: 14px; margin-top: 5px;">VitalCrop AGW Dashboard</p>
            </header>
            <main style="padding-top: 20px;">
                <h3 style="color: #374151;">Hola,</h3>
                <p style="color: #4b5563; line-height: 1.6;">
                    Has solicitado iniciar sesión en el Dashboard Agrícola. Usa el siguiente código de 6 dígitos para acceder a tu entorno seguro:
                </p>
                <div style="text-align: center; margin: 30px 0;">
                    <span style="font-size: 32px; font-weight: bold; letter-spacing: 5px; color: #10b981; padding: 10px 20px; border: 2px dashed #10b981; border-radius: 8px;">
                        {otp}
                    </span>
                </div>
                <p style="color: #4b5563; text-align: center; font-size: 14px;">
                    Este código expirará en <strong>10 minutos</strong>.
                </p>
            </main>
            <footer style="margin-top: 30px; border-top: 1px solid #e5e7eb; padding-top: 15px; text-align: center; font-size: 12px; color: #9ca3af;">
                <p>Si no solicitaste este código, puedes ignorar este correo de forma segura.</p>
                <p>© 2026 Noxum Soluciones IoT. Todos los derechos reservados.</p>
            </footer>
        </div>
    </body>
    </html>
    """
    msg.add_alternative(html_content, subtype='html')

    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)
            logger.info(f"Correo enviado exitosamente a {recipient}")
    except Exception as e:
        logger.error(f"Error enviando correo SMTP: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudo enviar el correo de verificación."
        )

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
            ORDER BY created_at DESC LIMIT 1
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
