"""
Auth service — login, refresh, user lookup
"""
from typing import Optional
import asyncpg
import uuid
from app.core.security import verify_password, hash_password, create_access_token, create_refresh_token, decode_token


class AuthService:
    def __init__(self, db: asyncpg.Connection):
        self.db = db

    async def get_user_by_email(self, email: str) -> Optional[dict]:
        row = await self.db.fetchrow(
            "SELECT id, email, full_name, role, is_active, hashed_password "
            "FROM users WHERE email=$1",
            email
        )
        return dict(row) if row else None

    async def get_user_by_id(self, user_id: str) -> Optional[dict]:
        row = await self.db.fetchrow(
            "SELECT id, email, full_name, role, is_active FROM users WHERE id=$1",
            uuid.UUID(user_id)
        )
        return dict(row) if row else None

    async def authenticate(self, email: str, password: str) -> Optional[dict]:
        user = await self.get_user_by_email(email)
        if not user:
            return None
        if not verify_password(password, user["hashed_password"]):
            return None
        return user

    async def create_tokens(self, user: dict) -> dict:
        access = create_access_token({"sub": str(user["id"]), "role": user["role"]})
        refresh = create_refresh_token({"sub": str(user["id"])})
        # Persist refresh token
        await self.db.execute(
            "UPDATE users SET refresh_token=$1 WHERE id=$2",
            refresh, user["id"]
        )
        return {"access_token": access, "refresh_token": refresh, "token_type": "bearer"}

    async def refresh_access_token(self, refresh_token: str) -> dict:
        try:
            payload = decode_token(refresh_token)
        except ValueError:
            raise ValueError("Invalid refresh token")
        if payload.get("type") != "refresh":
            raise ValueError("Not a refresh token")
        user_id = payload.get("sub")
        row = await self.db.fetchrow(
            "SELECT id, email, role, refresh_token FROM users WHERE id=$1",
            uuid.UUID(user_id)
        )
        if not row or row["refresh_token"] != refresh_token:
            raise ValueError("Refresh token revoked")
        user = dict(row)
        access = create_access_token({"sub": str(user["id"]), "role": user["role"]})
        return {"access_token": access, "refresh_token": refresh_token, "token_type": "bearer"}

    async def logout(self, user_id: str):
        await self.db.execute(
            "UPDATE users SET refresh_token=NULL WHERE id=$1",
            uuid.UUID(user_id)
        )

    async def create_user(self, email: str, password: str, full_name: str = None, role: str = "OPERATOR") -> dict:
        hashed = hash_password(password)
        row = await self.db.fetchrow(
            "INSERT INTO users (id, email, hashed_password, full_name, role) "
            "VALUES ($1, $2, $3, $4, $5) RETURNING id, email, full_name, role, is_active, created_at",
            uuid.uuid4(), email, hashed, full_name, role
        )
        return dict(row)
