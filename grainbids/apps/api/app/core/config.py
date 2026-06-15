from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    # Allow empty in early scaffolding; runtime should provide DATABASE_URL.
    database_url: str = ""
    api_cors_origins: str = "http://127.0.0.1:3000,http://localhost:3000"
    api_enable_docs: bool = True
    allow_implicit_org: bool = True
    auth_context_mode: str = "local_headers"
    allow_local_header_auth: bool = True
    daily_source_file_path: str = ""
    daily_source_name: str = "daily_source_file"
    daily_source_id: str = ""
    daily_commodity_id: str = ""
    reprocess_source_file_path_override: str = ""
    file_ingestion_max_attempts: int = 2
    canonical_min_quality_score: float = 0.8
    user_visible_facet_min_market_count: int = 2
    invalid_commodity_labels: str = "mixed daily file"
    canonical_aggregator_sources: str = "agricharts"
    canonical_aggregator_gap_threshold: float = 0.15
    alert_email_enabled: bool = False
    alert_email_from: str | None = None
    alert_email_to: str | None = None
    alert_smtp_host: str | None = None
    alert_smtp_port: int = 587
    alert_smtp_username: str | None = None
    alert_smtp_password: str | None = None
    alert_smtp_use_tls: bool = True

    @property
    def api_cors_origins_list(self) -> list[str]:
        return [origin.strip().rstrip("/") for origin in self.api_cors_origins.split(",") if origin.strip()]

    @property
    def invalid_commodity_labels_set(self) -> set[str]:
        return {token.strip().casefold() for token in self.invalid_commodity_labels.split(",") if token.strip()}

    @property
    def canonical_aggregator_sources_set(self) -> set[str]:
        return {token.strip().casefold() for token in self.canonical_aggregator_sources.split(",") if token.strip()}

    @model_validator(mode="after")
    def validate_runtime(self) -> "Settings":
        env = self.app_env.strip().lower()
        auth_context_mode = self.auth_context_mode.strip().lower()
        if auth_context_mode not in {"local_headers", "trusted_proxy"}:
            raise ValueError("AUTH_CONTEXT_MODE must be either local_headers or trusted_proxy")
        if env in {"production", "prod"}:
            if not self.database_url.strip():
                raise ValueError("DATABASE_URL is required when APP_ENV=production")
            if self.allow_implicit_org:
                raise ValueError("ALLOW_IMPLICIT_ORG must be false when APP_ENV=production")
            if auth_context_mode != "trusted_proxy":
                raise ValueError("AUTH_CONTEXT_MODE must be trusted_proxy when APP_ENV=production")
            if self.allow_local_header_auth:
                raise ValueError("ALLOW_LOCAL_HEADER_AUTH must be false when APP_ENV=production")
            if not self.api_cors_origins_list:
                raise ValueError("API_CORS_ORIGINS must include at least one origin when APP_ENV=production")
        self.auth_context_mode = auth_context_mode
        return self


settings = Settings()
