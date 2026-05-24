from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        protected_namespaces=(),  # model_path choca con el namespace model_ de pydantic
    )

    database_url: str
    api_key: str
    model_path: str = "models/damage_classifier.h5"
    rate_limit_per_minute: int = 120

    s3_endpoint_url: str
    s3_public_endpoint_url: str | None = None  # host que ve el cliente; firma las presigned URLs
    s3_access_key: str
    s3_secret_key: str
    s3_bucket: str = "car-images"
    s3_region: str = "us-east-1"
    s3_presigned_expiry: int = 3600


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
