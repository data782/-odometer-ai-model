from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = Field(default="fastapi-cloud-run-template", alias="APP_NAME")
    environment: str = Field(default="local", alias="ENVIRONMENT")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    service_version: str = Field(default="0.1.0", alias="SERVICE_VERSION")
    slow_request_ms: int = Field(default=1000, alias="SLOW_REQUEST_MS")
    odometer_api_key: SecretStr | None = Field(default=None, alias="ODOMETER_API_KEY")
    gemini_models: SecretStr | None = Field(default=None, alias="GEMINI_MODELS")
    gemini_api_key_1: SecretStr | None = Field(default=None, alias="GEMINI_API_KEY_1")
    gemini_api_key_2: SecretStr | None = Field(default=None, alias="GEMINI_API_KEY_2")
    gemini_api_key_3: SecretStr | None = Field(default=None, alias="GEMINI_API_KEY_3")
    gemini_api_key_4: SecretStr | None = Field(default=None, alias="GEMINI_API_KEY_4")
    gemini_api_key_5: SecretStr | None = Field(default=None, alias="GEMINI_API_KEY_5")

    otel_exporter_otlp_endpoint: str | None = Field(
        default=None, alias="OTEL_EXPORTER_OTLP_ENDPOINT"
    )
    otel_exporter_otlp_headers: SecretStr | None = Field(
        default=None, alias="OTEL_EXPORTER_OTLP_HEADERS"
    )
    cors_allowed_origins: str = Field(default="http://localhost:3000", alias="CORS_ALLOWED_ORIGINS")

    @property
    def observability_enabled(self) -> bool:
        return bool(self.otlp_endpoint and self.otlp_headers)

    @property
    def otlp_endpoint(self) -> str | None:
        return self.otel_exporter_otlp_endpoint

    @property
    def otlp_headers(self) -> str | None:
        if self.otel_exporter_otlp_headers:
            return self.otel_exporter_otlp_headers.get_secret_value()
        return None

    @property
    def odometer_auth_key(self) -> str | None:
        if self.odometer_api_key:
            return self.odometer_api_key.get_secret_value()
        return None

    @property
    def gemini_model_list(self) -> list[str]:
        if not self.gemini_models:
            return []
        return [m.strip() for m in self.gemini_models.get_secret_value().split(",") if m.strip()]

    @property
    def gemini_keys(self) -> list[str]:
        keys = [
            self.gemini_api_key_1,
            self.gemini_api_key_2,
            self.gemini_api_key_3,
            self.gemini_api_key_4,
            self.gemini_api_key_5,
        ]
        return [k.get_secret_value() for k in keys if k]

    @property
    def cors_allowed_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]

    def validate_runtime_settings(self) -> None:
        missing: list[str] = []
        if not self.odometer_auth_key:
            missing.append("ODOMETER_API_KEY")
        if not self.gemini_keys:
            missing.append("GEMINI_API_KEY_1..5")
        if not self.gemini_model_list:
            missing.append("GEMINI_MODELS")
        if missing:
            raise ValueError(f"Missing required runtime settings: {', '.join(missing)}")


@lru_cache
def get_settings() -> Settings:
    return Settings()
