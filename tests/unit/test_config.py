"""Tests for configuration settings and environment token resolution."""

from assistant.config import Settings


def test_effective_bot_token_production_default() -> None:
    settings = Settings(
        TELEGRAM_BOT_TOKEN="prod-token",
        TEST_TELEGRAM_BOT_TOKEN="test-token",
        ENVIRONMENT="production",
    )
    assert settings.effective_bot_token == "prod-token"


def test_effective_bot_token_staging_override() -> None:
    settings = Settings(
        TELEGRAM_BOT_TOKEN="prod-token",
        TEST_TELEGRAM_BOT_TOKEN="test-token",
        ENVIRONMENT="staging",
    )
    assert settings.effective_bot_token == "test-token"


def test_effective_bot_token_test_override() -> None:
    settings = Settings(
        TELEGRAM_BOT_TOKEN="prod-token",
        TEST_TELEGRAM_BOT_TOKEN="test-token",
        ENVIRONMENT="test",
    )
    assert settings.effective_bot_token == "test-token"


def test_effective_bot_token_fallback_when_only_test_set() -> None:
    settings = Settings(
        TELEGRAM_BOT_TOKEN="",
        TEST_TELEGRAM_BOT_TOKEN="test-token",
        ENVIRONMENT="production",
    )
    assert settings.effective_bot_token == "test-token"
