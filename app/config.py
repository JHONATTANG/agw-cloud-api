"""
Application settings loaded from environment variables.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List
import json


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # App
    APP_NAME: str = "AGW Cloud API"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # JWT
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Database
    DATABASE_URL: str
    SUPABASE_URL: str = ""
    SUPABASE_ANON_KEY: str = ""
    SUPABASE_SERVICE_KEY: str = ""

    # Edge Gateway
    EDGE_GATEWAY_TOKEN: str

    # CORS
    ALLOWED_ORIGINS: List[str] = ["http://localhost:3000"]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)


settings = Settings()
