"""
FastAPI dependencies for authentication and authorization
"""
from fastapi import Depends, HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.core.security import decode_token
from app.core.database import get_db
from app.config import settings
import asyncpg

bearer_scheme = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Security(bearer_scheme),
    db: asyncpg.Connection = Depends(get_db)
):
    token = credentials.credentials
    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Invalid token type")
        user_id = payload.get("sub")
        user = await db.fetchrow(
            "SELECT id, email, full_name, role, is_active FROM users WHERE id=$1", user_id
        )
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        if not user["is_active"]:
            raise HTTPException(status_code=403, detail="Inactive user")
        return dict(user)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))


async def get_edge_gateway(
    credentials: HTTPAuthorizationCredentials = Security(bearer_scheme),
):
    """Validates that the request comes from an authorized Edge Gateway."""
    if credentials.credentials != settings.EDGE_GATEWAY_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid edge token")
    return {"type": "edge_gateway"}


def require_role(role: str):
    """Returns a dependency that enforces a minimum role."""
    async def _require_role(current_user=Depends(get_current_user)):
        if current_user["role"] != role and current_user["role"] != "ADMIN":
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return current_user
    return _require_role
