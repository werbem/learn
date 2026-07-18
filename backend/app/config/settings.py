"""Application configuration via Pydantic BaseSettings.

Loads from:
  1. Environment variables (highest priority)
  2. .env file at project root
  3. .env file at backend/ root
  4. Default values (lowest priority)

Key env vars:
  OPENAI_API_KEY  — OpenAI API key (required for LLM_PROVIDER=openai)
  OPENAI_MODEL    — OpenAI model name (default: gpt-4o-mini)
  LLM_PROVIDER    — Provider: mock | openai | anthropic
"""

from __future__ import annotations

import warnings
from enum import Enum
from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict


# ── Load .env files before Pydantic initializes ──
# Priority: backend/.env > .env (project root)
_env_loaded = load_dotenv(override=False)  # project root .env
_env_loaded = load_dotenv(dotenv_path=".env", override=False) and _env_loaded


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

    # ── LLM Configuration ──
    # Set via environment variables or .env file
    llm_provider: LLMProvider = LLMProvider.MOCK

    # OpenAI — reads from OPENAI_API_KEY env var (no hardcoded default)
    openai_api_key: str = ""  # from OPENAI_API_KEY
    openai_model: str = "gpt-4o-mini"  # from OPENAI_MODEL
    openai_base_url: str = ""  # from OPENAI_BASE_URL

    # Tavily Search — reads from TAVILY_API_KEY env var
    tavily_api_key: str = ""  # from TAVILY_API_KEY
    # Legacy / alternative — reads from LLM_API_KEY (kept for backward compat)
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

    # ── LLM helpers ──

    @property
    def effective_api_key(self) -> str:
        """Return the first non-empty API key from all possible sources."""
        return self.openai_api_key or self.llm_api_key or ""

    @property
    def effective_model(self) -> str:
        """Return the model name."""
        return self.openai_model

    def validate_llm_config(self) -> list[str]:
        """Validate LLM configuration. Returns list of warning messages."""
        warnings_list: list[str] = []

        if self.llm_provider == LLMProvider.OPENAI:
            if not self.effective_api_key:
                warnings_list.append(
                    "LLM_PROVIDER=openai 但未配置 OPENAI_API_KEY。"
                    "请在 .env 文件中设置 OPENAI_API_KEY=sk-xxx，"
                    "或通过环境变量 export OPENAI_API_KEY=sk-xxx 配置。"
                    "将使用 Mock 模式回退。"
                )
            if not self.openai_model:
                warnings_list.append("OPENAI_MODEL 未设置，使用默认值 gpt-4o-mini")

        return warnings_list


settings = Settings()
