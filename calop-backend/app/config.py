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

    # AI food analysis (optional: without a key, captures are stored but not analysed)
    mistral_api_key: str | None = None
    mistral_model: str = "pixtral-12b-2409"
    min_analysis_weight_g: float = 1.0  # below this, nothing is "on the scale"

    max_image_bytes: int = 5 * 1024 * 1024
    cors_origins: str = "*"  # comma-separated list; tighten when the web app has a fixed URL

    @field_validator("database_url")
    @classmethod
    def _use_psycopg_driver(cls, v: str) -> str:
        # Supabase gives "postgresql://..."; SQLAlchemy needs the driver name.
        for prefix in ("postgres://", "postgresql://"):
            if v.startswith(prefix):
                return "postgresql+psycopg://" + v[len(prefix):]
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
