"""
Router — Authentication endpoints
"""
from fastapi import APIRouter, Depends, HTTPException
from app.schemas.auth import LoginRequest, TokenResponse, RefreshRequest, UserResponse
from app.services.auth_service import AuthService
from app.dependencies.auth import get_current_user
from app.core.database import get_db
import asyncpg

router = APIRouter(prefix="/api/auth", tags=["Auth"])


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: asyncpg.Connection = Depends(get_db)):
    service = AuthService(db)
    user = await service.authenticate(payload.email, payload.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    tokens = await service.create_tokens(user)
    return tokens


@router.post("/refresh", response_model=TokenResponse)
async def refresh(payload: RefreshRequest, db: asyncpg.Connection = Depends(get_db)):
    service = AuthService(db)
    try:
        tokens = await service.refresh_access_token(payload.refresh_token)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))
    return tokens


@router.get("/me", response_model=UserResponse)
async def me(current_user=Depends(get_current_user)):
    return current_user


@router.post("/logout", status_code=204)
async def logout(current_user=Depends(get_current_user), db: asyncpg.Connection = Depends(get_db)):
    service = AuthService(db)
    await service.logout(str(current_user["id"]))
