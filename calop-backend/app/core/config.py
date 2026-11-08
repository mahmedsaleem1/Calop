from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    supabase_url: str
    supabase_publishable_key: str
    cloudinary_cloud_name: str
    cloudinary_api_key: str
    cloudinary_api_secret: str

    vision_ai_provider: str = "gemini"  # label stored on each recognition run
    vision_ai_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/"
    vision_ai_api_key: str
    vision_ai_model: str
    vision_ai_reasoning_effort: str | None = "low"  # sent only if set; lowers latency
    vision_ai_timeout_seconds: float = 30
    vision_auto_log_threshold: float = 0.90

    local_image_dir: str = "storage/captures"
    max_device_image_bytes: int = 5 * 1024 * 1024
    max_phone_image_bytes: int = 12 * 1024 * 1024  # Gemini's inline request limit is 20 MB after base64
    worker_threads: int = 4
    cors_origins: str = "*"  # comma-separated list

    @field_validator("database_url")
    @classmethod
    def _use_psycopg_driver(cls, url: str) -> str:
        # Supabase gives "postgresql://..."; SQLAlchemy needs the driver name.
        for prefix in ("postgres://", "postgresql://"):
            if url.startswith(prefix):
                return "postgresql+psycopg://" + url[len(prefix):]
        return url


@lru_cache
def get_settings() -> Settings:
    return Settings()
