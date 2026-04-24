from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    # Allow empty in early scaffolding; runtime should provide DATABASE_URL.
    database_url: str = ""
    allow_implicit_org: bool = True
    daily_source_file_path: str = ""
    daily_source_name: str = "daily_source_file"
    daily_source_id: str = ""
    daily_commodity_id: str = ""
    file_ingestion_max_attempts: int = 2
    alert_email_enabled: bool = False
    alert_email_from: str | None = None
    alert_email_to: str | None = None
    alert_smtp_host: str | None = None
    alert_smtp_port: int = 587
    alert_smtp_username: str | None = None
    alert_smtp_password: str | None = None
    alert_smtp_use_tls: bool = True


settings = Settings()
