"""Application configuration via Pydantic BaseSettings."""

from __future__ import annotations

from enum import Enum
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class AppEnv(str, Enum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class LLMProvider(str, Enum):
    MOCK = "mock"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"


class LogFormat(str, Enum):
    JSON = "json"
    TEXT = "text"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "competitive-analysis-backend"
    app_env: AppEnv = AppEnv.DEVELOPMENT
    app_debug: bool = True
    app_port: int = 8000
    app_host: str = "0.0.0.0"

    # Database
    database_url: str = "sqlite+aiosqlite:///./data/competitive_analysis.db"
    database_echo: bool = False

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # LLM
    llm_provider: LLMProvider = LLMProvider.MOCK
    llm_model: str = "gpt-4o"
    llm_api_key: str = ""

    # Logging
    log_level: str = "INFO"
    log_format: LogFormat = LogFormat.JSON

    # Workflow
    workflow_max_duration_seconds: int = 300
    workflow_max_retries: int = 3
    workflow_hitl_enabled: bool = False

    # Paths
    project_root: Path = Path(__file__).resolve().parent.parent.parent.parent

    @property
    def data_dir(self) -> Path:
        path = self.project_root / "data"
        path.mkdir(parents=True, exist_ok=True)
        return path


settings = Settings()
