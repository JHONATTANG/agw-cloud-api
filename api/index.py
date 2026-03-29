"""
api/index.py — Vercel Serverless entry point for agw-cloud-api
==============================================================
This module is the single file that Vercel executes as a Python
Serverless Function.  It bootstraps a lightweight FastAPI app that:

  • Connects to Supabase via the *Transaction Pooler* (port 6543) using
    psycopg2 (synchronous), which is compatible with serverless cold-starts
    because connection pools are opened per-request.
  • Exposes a static Bearer Token middleware (reads API_TOKEN env var).
  • Provides the three required endpoints:
      GET  /              → root health check
      GET  /api/health    → detailed health check
      POST /api/telemetria        → ingest telemetry from Fog Node
      GET  /api/telemetria/{node_id} → last 50 records for a node

Environment variables (set in Vercel project settings):
  DATABASE_URL  – Transaction Pooler connection string (port 6543)
  API_TOKEN     – Static Bearer token shared with the Raspberry Pi gateway

Author: Noxum Soluciones / agw-cloud-api
"""

import os
import json
import logging
from datetime import datetime, timezone
from typing import Optional

import psycopg2
import psycopg2.extras
from fastapi import FastAPI, HTTPException, Depends, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("agw-cloud-api")

# ---------------------------------------------------------------------------
# Configuration — loaded from environment at cold-start
# ---------------------------------------------------------------------------
DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    # Fallback: Supabase Transaction Pooler (development only)
    "postgresql://postgres.sayqxmtvqaeyxhyptgpw:pg-crops-+4@aws-1-us-east-1.pooler.supabase.com:6543/postgres",
)

API_TOKEN: str = os.getenv("API_TOKEN", "dev-token-change-in-production")

# ---------------------------------------------------------------------------
# FastAPI app instance
# ---------------------------------------------------------------------------
app = FastAPI(
    title="AGW Cloud API — Noxum Soluciones",
    version="2.0.0",
    description=(
        "Fog Computing backend para el sistema de cultivo hidropónico de hierbabuena. "
        "Recibe telemetría de nodos ESP32 orquestados por un Gateway Raspberry Pi."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # Lock down in production via env var
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Security — Static Bearer Token
# ---------------------------------------------------------------------------
bearer_scheme = HTTPBearer(auto_error=False)


async def require_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> str:
    """Dependency: validates the static Bearer token sent by the Fog Node."""
    if credentials is None or credentials.credentials != API_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de autorización inválido o ausente.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return credentials.credentials


# ---------------------------------------------------------------------------
# Database helpers (synchronous psycopg2 — Transaction Pooler safe)
# ---------------------------------------------------------------------------
def get_connection() -> psycopg2.extensions.connection:
    """Open a fresh connection from the Transaction Pooler."""
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
    conn.autocommit = False
    return conn


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------
class TelemetriaPayload(BaseModel):
    """Body esperado del POST /api/telemetria."""

    node_id: str = Field(
        ...,
        min_length=3,
        max_length=64,
        description="Identificador único del nodo Fog/Gateway (ej. FOG_RPI_HIERBABUENA_01)",
        examples=["FOG_RPI_HIERBABUENA_01"],
    )
    sensor_id: str = Field(
        ...,
        min_length=3,
        max_length=64,
        description="Identificador del sensor ESP32 origen (ej. ESP32_ZONA_A)",
        examples=["ESP32_ZONA_A"],
    )
    temperatura: Optional[float] = Field(
        None, ge=-40.0, le=100.0, description="Temperatura ambiente en °C"
    )
    humedad_ambiente: Optional[float] = Field(
        None, ge=0.0, le=100.0, description="Humedad relativa del aire en %"
    )
    humedad_suelo: Optional[float] = Field(
        None, ge=0.0, le=100.0, description="Humedad del sustrato/solución en %"
    )
    ph: Optional[float] = Field(
        None, ge=0.0, le=14.0, description="pH de la solución nutritiva"
    )
    estado_actuadores: Optional[str] = Field(
        None,
        max_length=255,
        description="Estado de actuadores como texto o JSON serializado",
        examples=['{"bomba": "ON", "lampara": "ON", "ventilador": "OFF"}'],
    )


class TelemetriaResponse(BaseModel):
    """Respuesta de un registro de telemetría."""

    id: int
    created_at: datetime
    node_id: str
    sensor_id: str
    temperatura: Optional[float]
    humedad_ambiente: Optional[float]
    humedad_suelo: Optional[float]
    ph: Optional[float]
    estado_actuadores: Optional[str]

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Routes — Health
# ---------------------------------------------------------------------------
@app.get("/", tags=["Health"], summary="Root health check")
async def root():
    """Punto de entrada raíz. Responde 200 para evitar 404 en Vercel."""
    return {
        "service": "AGW Cloud API",
        "version": "2.0.0",
        "organization": "Noxum Soluciones",
        "status": "operational",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/health", tags=["Health"], summary="Detailed health check")
async def health_check():
    """
    Verifica la conectividad con la base de datos PostgreSQL (Supabase).
    Usado por Vercel para validar que la función serverless responde.
    """
    db_status = "unknown"
    db_latency_ms: Optional[float] = None

    try:
        t0 = datetime.now(timezone.utc)
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT 1 AS alive;")
        cur.fetchone()
        cur.close()
        conn.close()
        db_latency_ms = round(
            (datetime.now(timezone.utc) - t0).total_seconds() * 1000, 2
        )
        db_status = "connected"
    except Exception as exc:
        logger.error("Health check — DB connection failed: %s", exc)
        db_status = "unreachable"

    return {
        "status": "ok" if db_status == "connected" else "degraded",
        "version": "2.0.0",
        "database": {
            "status": db_status,
            "latency_ms": db_latency_ms,
            "pooler": "supabase-transaction-pooler",
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Routes — Telemetría
# ---------------------------------------------------------------------------
@app.post(
    "/api/telemetria",
    status_code=status.HTTP_201_CREATED,
    tags=["Telemetría"],
    summary="Ingerir telemetría de un nodo Fog",
    response_description="Registro insertado exitosamente",
)
async def post_telemetria(
    payload: TelemetriaPayload,
    _token: str = Depends(require_token),
):
    """
    Recibe lecturas de sensores del Gateway Raspberry Pi y las persiste
    en la tabla `telemetria_indoor` de Supabase.

    **Requiere** header: `Authorization: Bearer <API_TOKEN>`
    """
    INSERT_SQL = """
        INSERT INTO telemetria_indoor
            (node_id, sensor_id, temperatura, humedad_ambiente,
             humedad_suelo, ph, estado_actuadores)
        VALUES
            (%(node_id)s, %(sensor_id)s, %(temperatura)s, %(humedad_ambiente)s,
             %(humedad_suelo)s, %(ph)s, %(estado_actuadores)s)
        RETURNING id, created_at;
    """
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(INSERT_SQL, payload.model_dump())
        row = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
    except Exception as exc:
        logger.error("Error al insertar telemetría: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al persistir la telemetría: {exc}",
        )

    return {
        "status": "created",
        "id": row["id"],
        "created_at": row["created_at"].isoformat(),
        "node_id": payload.node_id,
        "sensor_id": payload.sensor_id,
    }


@app.get(
    "/api/telemetria/{node_id}",
    tags=["Telemetría"],
    summary="Obtener últimos 50 registros de un nodo",
    response_description="Lista de registros de telemetría",
)
async def get_telemetria(
    node_id: str,
    _token: str = Depends(require_token),
):
    """
    Retorna los **últimos 50 registros** de telemetría para el `node_id`
    especificado, ordenados del más reciente al más antiguo.

    **Requiere** header: `Authorization: Bearer <API_TOKEN>`
    """
    SELECT_SQL = """
        SELECT id, created_at, node_id, sensor_id,
               temperatura, humedad_ambiente, humedad_suelo,
               ph, estado_actuadores
        FROM   telemetria_indoor
        WHERE  node_id = %(node_id)s
        ORDER BY created_at DESC
        LIMIT  50;
    """
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(SELECT_SQL, {"node_id": node_id})
        rows = cur.fetchall()
        cur.close()
        conn.close()
    except Exception as exc:
        logger.error("Error al consultar telemetría: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al consultar la telemetría: {exc}",
        )

    # Serialize datetimes to ISO 8601 strings
    records = []
    for row in rows:
        r = dict(row)
        if isinstance(r.get("created_at"), datetime):
            r["created_at"] = r["created_at"].isoformat()
        records.append(r)

    return {
        "node_id": node_id,
        "count": len(records),
        "records": records,
    }


# ---------------------------------------------------------------------------
# Vercel handler — ASGI adapter
# ---------------------------------------------------------------------------
# Vercel imports `app` directly as an ASGI app via the `builds` config.
# Nothing extra needed; just expose `app` at module level (done above).

# Ping redeploy: 2026-03-28 19:22:33
