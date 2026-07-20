import logging
import re
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ApiKeyFilter(logging.Filter):
    """Маскирует API-ключ в логах."""

    def __init__(self, api_key: str = "") -> None:
        super().__init__()
        if api_key and isinstance(api_key, str) and len(api_key) > 3:
            self._pattern: re.Pattern[str] | None = re.compile(re.escape(api_key))
        else:
            self._pattern = None

    def filter(self, record: logging.LogRecord) -> bool:
        if self._pattern and isinstance(record.msg, str):
            record.msg = self._pattern.sub("***", record.msg)
        if self._pattern and record.args and isinstance(record.args, tuple):
            record.args = tuple(
                self._pattern.sub("***", str(a)) if isinstance(a, str) else a for a in record.args
            )
        return True


class Settings(BaseSettings):
    """Настройки приложения из переменных окружения."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="TRAFFIC_",
        extra="ignore",
    )

    yandex_api_key: str = Field(default="", alias="YANDEX_API_KEY")
    database_path: Path = Path("data/traffic.sqlite3")
    segments_config: Path = Path("config/segments.yaml")
    request_timeout_seconds: float = 15.0
    collection_interval_seconds: int = 300
    timezone: str = "Asia/Almaty"


def load_settings() -> Settings:
    """Загружает настройки из переменных окружения и .env файла."""
    return Settings()
