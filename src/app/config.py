from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Payment Processing Service"
    api_key: str = Field(default="dev-api-key", min_length=8)
    database_url: str = "postgresql+asyncpg://payments:payments@localhost:5432/payments"
    rabbitmq_url: str = "amqp://payments:payments@localhost:5672/"

    gateway_min_delay_seconds: float = Field(default=2, ge=0)
    gateway_max_delay_seconds: float = Field(default=5, ge=0)
    gateway_success_rate: float = Field(default=0.9, ge=0, le=1)

    webhook_timeout_seconds: float = Field(default=5, gt=0)
    webhook_max_attempts: int = Field(default=3, ge=1, le=10)
    outbox_poll_interval_seconds: float = Field(default=1, gt=0)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

