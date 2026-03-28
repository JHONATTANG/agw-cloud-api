"""
VitalCrop AGW Cloud API — Application Factory
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import structlog

from app.config import settings
from app.core.database import init_db, close_db
from app.core.middleware import LoggingMiddleware, RateLimitMiddleware
from app.routers import auth, devices, telemetry, commands, alerts

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage startup/shutdown lifecycle."""
    logger.info("Starting AGW Cloud API", version=settings.APP_VERSION)
    await init_db()
    yield
    await close_db()
    logger.info("AGW Cloud API shut down")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description="VitalCrop AGW — Cloud REST API for IoT fleet management",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # ── CORS ──────────────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Custom middleware ─────────────────────────────────────────────────────
    app.add_middleware(LoggingMiddleware)
    app.add_middleware(RateLimitMiddleware, max_requests=200, window_seconds=60)

    # ── Routers ───────────────────────────────────────────────────────────────
    app.include_router(auth.router)
    app.include_router(devices.router)
    app.include_router(telemetry.router)
    app.include_router(commands.router)
    app.include_router(alerts.router)

    # ── Health check ──────────────────────────────────────────────────────────
    @app.get("/health", tags=["Health"])
    async def health():
        return {"status": "ok", "version": settings.APP_VERSION}

    return app


app = create_app()
