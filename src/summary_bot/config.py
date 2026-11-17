"""Configuration settings for SummaryBot."""

import os
from enum import StrEnum
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class TaskCategory(StrEnum):
    """Categories of incoming workloads."""

    AUDIO_VIDEO = "audio_video"
    TEXT_DOCS = "text_docs"
    VISION = "vision"
    MICRO = "micro"
    PRO = "pro"


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file."""

    model_config = SettingsConfigDict(
        env_file=(
            "/home/apps/stacks/SummaryBot/.env",
            "/host/stacks/agent/SummaryBot/.env",
            "/home/agent/stacks/agent/SummaryBot/.env",
            ".env",
        ),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # OpenRouter API settings
    openrouter_api_key: str = Field(default="", alias="OPENROUTER_API_KEY")
    openrouter_base_url: str = Field(
        default="https://openrouter.ai/api/v1", alias="OPENROUTER_BASE_URL"
    )
    openrouter_http_referer: str = Field(default="https://nada.mu", alias="OPENROUTER_HTTP_REFERER")
    openrouter_app_title: str = Field(default="SummaryBot", alias="OPENROUTER_APP_TITLE")

    # Environment mode (production, staging, test)
    environment: str = Field(default="production", alias="ENVIRONMENT")

    # Telegram settings
    telegram_bot_token: str = Field(default="", alias="TELEGRAM_BOT_TOKEN")
    test_telegram_bot_token: str = Field(default="", alias="TEST_TELEGRAM_BOT_TOKEN")

    @field_validator(
        "telegram_bot_token", "test_telegram_bot_token", "openrouter_api_key", mode="before"
    )
    @classmethod
    def sanitize_secrets(cls, v: str | None) -> str | None:
        if isinstance(v, str):
            return v.strip().strip("\"'")
        return v

    @property
    def effective_bot_token(self) -> str:
        """Resolve active Telegram bot token based on environment."""
        if (
            self.environment.lower() in ("test", "staging", "dev", "development")
            and self.test_telegram_bot_token
        ):
            return self.test_telegram_bot_token
        return self.telegram_bot_token or self.test_telegram_bot_token

    # Primary and Fallback model mapping
    model_audio_primary: str = Field(default="xiaomi/mimo-v2.6-flash", alias="MODEL_AUDIO_PRIMARY")
    model_audio_fallback: str = Field(
        default="qwen/qwen3.8-omni-flash", alias="MODEL_AUDIO_FALLBACK"
    )

    model_text_primary: str = Field(
        default="thinkingmachines/inkling-2-small:free", alias="MODEL_TEXT_PRIMARY"
    )
    model_text_fallback: str = Field(default="z-ai/glm-5.3-flash", alias="MODEL_TEXT_FALLBACK")

    model_vision_primary: str = Field(
        default="thinkingmachines/inkling-2-small:free", alias="MODEL_VISION_PRIMARY"
    )
    model_vision_fallback: str = Field(default="z-ai/glm-5.3-flash", alias="MODEL_VISION_FALLBACK")

    model_micro_primary: str = Field(default="z-ai/glm-5.3-flash", alias="MODEL_MICRO_PRIMARY")
    model_micro_fallback: str = Field(
        default="deepseek/deepseek-v4.1-flash", alias="MODEL_MICRO_FALLBACK"
    )

    model_pro_primary: str = Field(default="z-ai/glm-5.3", alias="MODEL_PRO_PRIMARY")
    model_pro_fallback: str = Field(default="google/gemini-3.8-flash", alias="MODEL_PRO_FALLBACK")

    # Limits and timeouts
    request_timeout_seconds: float = Field(default=90.0, alias="REQUEST_TIMEOUT_SECONDS")
    max_retries: int = Field(default=2, alias="MAX_RETRIES")
    max_download_size_bytes: int = Field(
        default=52_428_800,
        alias="MAX_DOWNLOAD_SIZE_BYTES",  # 50 MB
    )

    # Storage and database settings
    data_dir: Path = Field(
        default_factory=lambda: Path(
            os.environ.get(
                "SUMMARY_BOT_DATA_DIR",
                "/app/data"
                if Path("/app/data").is_dir()
                else str(Path.home() / ".local" / "share" / "summary-bot"),
            )
        ),
        alias="SUMMARY_BOT_DATA_DIR",
    )

    @property
    def db_path(self) -> Path:
        """Absolute path to the SQLite persistence database."""
        return self.data_dir / "summarybot.db"

    def get_models_for_category(self, category: TaskCategory) -> tuple[str, str]:
        """Return (primary_model, fallback_model) for a given category."""
        match category:
            case TaskCategory.AUDIO_VIDEO:
                return (self.model_audio_primary, self.model_audio_fallback)
            case TaskCategory.TEXT_DOCS:
                return (self.model_text_primary, self.model_text_fallback)
            case TaskCategory.VISION:
                return (self.model_vision_primary, self.model_vision_fallback)
            case TaskCategory.MICRO:
                return (self.model_micro_primary, self.model_micro_fallback)
            case TaskCategory.PRO:
                return (self.model_pro_primary, self.model_pro_fallback)


settings = Settings()
