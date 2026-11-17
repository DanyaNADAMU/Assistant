"""Unit tests for operational telemetry, diagnostics, and healthcheck services."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import CallbackQuery, Message, User

from summary_bot.adapters.storage.preferences_repository import SqlitePreferencesRepository
from summary_bot.core.models.user_preferences import UserPreferences
from summary_bot.core.ports.cache import CacheStats
from summary_bot.core.services.telemetry import TelemetryService, TelemetrySnapshot
from summary_bot.interfaces.telegram.handlers.callbacks import handle_status_action
from summary_bot.interfaces.telegram.handlers.commands import cmd_status
from summary_bot.interfaces.telegram.keyboards import get_status_keyboard


def test_format_uptime() -> None:
    """Verify human-readable uptime formatting across granular intervals."""
    base = datetime.now(UTC)

    # 45 seconds ago
    service_45s = TelemetryService(started_at=base - timedelta(seconds=45))
    assert service_45s.format_uptime() == "45с"

    # 2 minutes 15 seconds ago
    service_2m = TelemetryService(started_at=base - timedelta(minutes=2, seconds=15))
    assert service_2m.format_uptime() == "2м 15с"

    # 3 hours 20 minutes 5 seconds ago
    service_3h = TelemetryService(started_at=base - timedelta(hours=3, minutes=20, seconds=5))
    assert service_3h.format_uptime() == "3ч 20м 5с"

    # 2 days 4 hours 10 minutes 12 seconds ago
    service_2d = TelemetryService(
        started_at=base - timedelta(days=2, hours=4, minutes=10, seconds=12)
    )
    assert service_2d.format_uptime() == "2д 4ч 10м 12с"


def test_memory_usage() -> None:
    """Verify that RSS memory reading returns a reasonable non-negative value."""
    service = TelemetryService()
    rss = service.get_memory_usage_mb()
    assert isinstance(rss, float)
    assert rss >= 0.0


def test_storage_stats_and_healthcheck(tmp_path: Path) -> None:
    """Verify database size computation, user count querying, and healthcheck."""
    db_file = tmp_path / "telemetry_test.db"
    service = TelemetryService(db_path=db_file)

    assert service.is_healthy() is True

    # Initialize preferences repository to create table and add user
    repo = SqlitePreferencesRepository(db_path=db_file)
    pref = UserPreferences(user_id=12345)
    repo._save_sync(pref)

    db_kb, wal_kb, user_count = service._get_storage_stats_sync()
    assert db_kb > 0.0
    assert wal_kb >= 0.0
    assert user_count == 1


@pytest.mark.asyncio
async def test_telemetry_snapshot_formatting() -> None:
    """Verify markdown diagnostic report rendering."""
    snapshot = TelemetrySnapshot(
        environment="staging",
        uptime_seconds=3665.0,
        uptime_formatted="1ч 1м 5с",
        memory_rss_mb=145.2,
        db_size_kb=512.0,
        wal_size_kb=64.0,
        registered_users=8,
        cache_stats=CacheStats(
            summary_count=20,
            summary_hits=45,
            refinement_count=10,
            refinement_hits=15,
        ),
        active_models={"audio_video": "gemini-flash", "text_docs": "gemini-flash"},
    )

    report = snapshot.format_telegram_report()
    assert "📊 **Диагностика и статус SummaryBot**" in report
    assert "(`staging`)" in report
    assert "`1ч 1м 5с`" in report
    assert "`145.2 МБ`" in report
    assert "• Саммари в базе: `20`" in report
    assert "• Попаданий в кэш: `45`" in report
    assert "• Эффективность (Hit Rate): `66.7%`" in report


def test_status_keyboard() -> None:
    """Verify status inline keyboard buttons."""
    markup = get_status_keyboard()
    assert len(markup.inline_keyboard) == 1
    buttons = markup.inline_keyboard[0]
    assert len(buttons) == 2
    assert buttons[0].callback_data == "status:refresh"
    assert buttons[1].callback_data == "status:settings"


@pytest.mark.asyncio
async def test_cmd_status_handler() -> None:
    """Verify /status command handler replies with formatted telemetry card."""
    mock_message = MagicMock(spec=Message)
    mock_message.answer = AsyncMock()

    await cmd_status(mock_message)
    mock_message.answer.assert_called_once()
    args, kwargs = mock_message.answer.call_args
    assert "📊 **Диагностика и статус SummaryBot**" in args[0]
    assert kwargs.get("parse_mode") == "Markdown"
    assert kwargs.get("reply_markup") is not None


@pytest.mark.asyncio
async def test_status_callbacks() -> None:
    """Verify status refresh and settings transition callbacks."""
    mock_user = MagicMock(spec=User)
    mock_user.id = 999
    mock_user.username = "testowner"

    mock_msg = MagicMock(spec=Message)
    mock_msg.edit_text = AsyncMock()

    # Test refresh
    cb_refresh = MagicMock(spec=CallbackQuery)
    cb_refresh.data = "status:refresh"
    cb_refresh.message = mock_msg
    cb_refresh.from_user = mock_user
    cb_refresh.answer = AsyncMock()

    await handle_status_action(cb_refresh)
    cb_refresh.answer.assert_called_once_with("Данные обновлены ✅")
    mock_msg.edit_text.assert_called_once()

    # Test settings transition
    mock_msg.edit_text.reset_mock()
    cb_settings = MagicMock(spec=CallbackQuery)
    cb_settings.data = "status:settings"
    cb_settings.message = mock_msg
    cb_settings.from_user = mock_user
    cb_settings.answer = AsyncMock()

    await handle_status_action(cb_settings)
    mock_msg.edit_text.assert_called_once()
    args, _ = mock_msg.edit_text.call_args
    assert "Настройки бота SummaryBot" in args[0]
