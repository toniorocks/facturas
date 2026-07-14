from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class Settings(BaseSettings):
    GEMINI_API_KEY: str = Field(default="your_gemini_api_key_here")
    DATABASE_URL: str = Field(default="postgresql+asyncpg://postgres:postgres_secure_pass@localhost:5432/facturas_db")
    ENV: str = "development"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
