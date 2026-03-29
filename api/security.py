import os
import jwt
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import psycopg2.extras
from pydantic import BaseModel

# Evitamos importar app completa para evitar circular imports, 
# podemos reutilizar get_connection si abrimos una funcion local o lo importamos
# Para evitar dependencias circulares, pasaremos la conexion o la abriremos aqui:
import psycopg2

logger = logging.getLogger("agw-cloud-api.security")

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres.sayqxmtvqaeyxhyptgpw:pg-crops-+4@aws-1-us-east-1.pooler.supabase.com:6543/postgres",
)
API_TOKEN = os.getenv("API_TOKEN", "dev-token-change-in-production")
JWT_SECRET = os.getenv("JWT_SECRET", "change-me-in-production")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440")) # 24 horas por defecto

bearer_scheme = HTTPBearer(auto_error=False)

def get_db_connection():
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
    conn.autocommit = False
    return conn

# ---------------------------------------------------------------------------
# IoT Static Token Security
# ---------------------------------------------------------------------------
async def require_iot_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> str:
    """Dependency: validates the static Bearer token sent by the Fog Node."""
    if credentials is None or credentials.credentials != API_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de autorización IoT inválido o ausente.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return credentials.credentials

# ---------------------------------------------------------------------------
# JWT Human User Security
# ---------------------------------------------------------------------------
class TokenData(BaseModel):
    user_id: str
    email: str

def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return encoded_jwt

async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> dict:
    """Dependency: validates JWT and returns current user from DB."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token no provisto.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = credentials.credentials
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token no contiene user ID (sub).")
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expirado.")
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Token inválido: {e}")

    # Obtener el usuario de la BDD
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, email, full_name, created_at FROM public.users WHERE id = %s", (user_id,))
        user_row = cur.fetchone()
        cur.close()
        conn.close()
    except Exception as exc:
        logger.error("Error consultando usuario en la DB: %s", exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error de base de datos")

    if user_row is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario no encontrado.")

    return dict(user_row)
