"""Application settings and environment configuration."""
import os
from pydantic import ConfigDict
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = ConfigDict(env_file=".env", extra="allow")

    PROJECT_NAME: str = "CardArena"
    API_V1_STR: str = "/api/v1"
    SECRET_KEY: str = "cardarena-super-secret-development-key-change-in-prod"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 1 day

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/cardarena"
    SQL_DEBUG: bool = False

    # CORS
    BACKEND_CORS_ORIGINS: list[str] = ["*"]


settings = Settings()
