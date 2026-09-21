from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    db_user: str
    db_password: str
    db_host: str
    db_port: int = 1521
    db_service: str

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @property
    def db_dsn(self) -> str:
        return f"{self.db_host}:{self.db_port}/{self.db_service}"


settings = Settings()
