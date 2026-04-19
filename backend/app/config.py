from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    xe_account_id: str = ""
    xe_api_key: str = ""
    api_secret_key: str = ""
    database_url: str = ""
    rates_fallback: bool = False

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
