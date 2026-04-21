from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    # Allow empty in early scaffolding; runtime should provide DATABASE_URL.
    database_url: str = ""
    daily_source_file_path: str = ""
    daily_source_name: str = "daily_source_file"
    daily_source_id: str = ""
    daily_commodity_id: str = ""


settings = Settings()
