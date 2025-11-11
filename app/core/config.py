from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List, Optional


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", case_sensitive=False)

    # Core
    APP_NAME: str = "CostChecker"
    ENV: str = "dev"

    # Database
    DATABASE_URL: str = "postgresql+psycopg2://postgres:postgres@127.0.0.1:5432/costchecker"

    # DeepSeek
    DEEPSEEK_API_KEY: Optional[str] = None

    # Admin
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "change-me"

    # CORS
    CORS_ORIGINS: List[str] = ["*"]


settings = Settings()
