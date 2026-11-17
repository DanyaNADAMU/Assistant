"""Unit tests for user preferences model, repository, prompts, and keyboard."""

import pytest

from summary_bot.adapters.storage.preferences_repository import SqlitePreferencesRepository
from summary_bot.config import TaskCategory
from summary_bot.core.models.user_preferences import (
    OutputFormat,
    OutputLanguage,
    SummaryDepth,
    UserPreferences,
)
from summary_bot.core.services.prompts import get_prompt_for_category
from summary_bot.interfaces.telegram.keyboards import get_settings_keyboard


class TestUserPreferencesModel:
    """Test domain model methods and cycling."""

    def test_default_preferences(self) -> None:
        prefs = UserPreferences.default_for_user(12345)
        assert prefs.user_id == 12345
        assert prefs.language == OutputLanguage.AUTO
        assert prefs.depth == SummaryDepth.STANDARD
        assert prefs.format == OutputFormat.STANDARD
        assert prefs.include_action_items is False

    def test_cycle_language(self) -> None:
        prefs = UserPreferences.default_for_user(1)
        assert prefs.language == OutputLanguage.AUTO
        assert prefs.next_language() == OutputLanguage.RU
        prefs.language = OutputLanguage.RU
        assert prefs.next_language() == OutputLanguage.EN
        prefs.language = OutputLanguage.EN
        assert prefs.next_language() == OutputLanguage.AUTO

    def test_cycle_depth(self) -> None:
        prefs = UserPreferences.default_for_user(1)
        assert prefs.depth == SummaryDepth.STANDARD
        assert prefs.next_depth() == SummaryDepth.DETAILED
        prefs.depth = SummaryDepth.DETAILED
        assert prefs.next_depth() == SummaryDepth.CONCISE
        prefs.depth = SummaryDepth.CONCISE
        assert prefs.next_depth() == SummaryDepth.STANDARD

    def test_cycle_format(self) -> None:
        prefs = UserPreferences.default_for_user(1)
        assert prefs.format == OutputFormat.STANDARD
        assert prefs.next_format() == OutputFormat.BULLETS
        prefs.format = OutputFormat.BULLETS
        assert prefs.next_format() == OutputFormat.STANDARD

    def test_format_settings_card(self) -> None:
        prefs = UserPreferences.default_for_user(999)
        card = prefs.format_settings_card(username="alice")
        assert "@alice" in card
        assert "Авто" in card
        assert "Стандартная" in card
        assert "Выключен" in card

        prefs.include_action_items = True
        card2 = prefs.format_settings_card()
        assert "ID: 999" in card2
        assert "Включен" in card2


class TestSqlitePreferencesRepository:
    """Test SQLite storage persistence."""

    @pytest.mark.asyncio
    async def test_get_defaults_for_unknown_user(self, tmp_path) -> None:
        repo = SqlitePreferencesRepository(db_path=tmp_path / "test.db")
        prefs = await repo.get(42)
        assert prefs.user_id == 42
        assert prefs.language == OutputLanguage.AUTO
        assert prefs.depth == SummaryDepth.STANDARD
        assert prefs.include_action_items is False

    @pytest.mark.asyncio
    async def test_save_and_retrieve_preferences(self, tmp_path) -> None:
        repo = SqlitePreferencesRepository(db_path=tmp_path / "test.db")
        prefs = await repo.get(100)
        prefs.language = OutputLanguage.RU
        prefs.depth = SummaryDepth.DETAILED
        prefs.format = OutputFormat.BULLETS
        prefs.include_action_items = True

        await repo.save(prefs)

        loaded = await repo.get(100)
        assert loaded.user_id == 100
        assert loaded.language == OutputLanguage.RU
        assert loaded.depth == SummaryDepth.DETAILED
        assert loaded.format == OutputFormat.BULLETS
        assert loaded.include_action_items is True

    @pytest.mark.asyncio
    async def test_reset_preferences(self, tmp_path) -> None:
        repo = SqlitePreferencesRepository(db_path=tmp_path / "test.db")
        prefs = await repo.get(200)
        prefs.language = OutputLanguage.EN
        prefs.include_action_items = True
        await repo.save(prefs)

        reset_prefs = await repo.reset(200)
        assert reset_prefs.language == OutputLanguage.AUTO
        assert reset_prefs.include_action_items is False

        retrieved = await repo.get(200)
        assert retrieved.language == OutputLanguage.AUTO
        assert retrieved.include_action_items is False


class TestPromptsWithPreferences:
    """Test prompt enrichment based on user settings."""

    def test_base_prompt_without_preferences(self) -> None:
        base = get_prompt_for_category(TaskCategory.TEXT_DOCS)
        assert "Пользовательские предпочтения" not in base

    def test_prompt_with_russian_language(self) -> None:
        prefs = UserPreferences.default_for_user(1)
        prefs.language = OutputLanguage.RU
        prompt = get_prompt_for_category(TaskCategory.TEXT_DOCS, preferences=prefs)
        assert "Пользовательские предпочтения" in prompt
        assert (
            "Языковое требование: Твой ответ должен быть строго на чистом русском языке" in prompt
        )

    def test_prompt_with_english_language(self) -> None:
        prefs = UserPreferences.default_for_user(1)
        prefs.language = OutputLanguage.EN
        prompt = get_prompt_for_category(TaskCategory.TEXT_DOCS, preferences=prefs)
        assert "Language requirement: Provide your complete response in clear" in prompt

    def test_prompt_with_concise_depth(self) -> None:
        prefs = UserPreferences.default_for_user(1)
        prefs.depth = SummaryDepth.CONCISE
        prompt = get_prompt_for_category(TaskCategory.TEXT_DOCS, preferences=prefs)
        assert "Глубина изложения: Будь предельно лаконичен" in prompt

    def test_prompt_with_detailed_depth(self) -> None:
        prefs = UserPreferences.default_for_user(1)
        prefs.depth = SummaryDepth.DETAILED
        prompt = get_prompt_for_category(TaskCategory.TEXT_DOCS, preferences=prefs)
        assert "Глубина изложения: Предоставь максимально детальный и всесторонний разбор" in prompt

    def test_prompt_with_action_items(self) -> None:
        prefs = UserPreferences.default_for_user(1)
        prefs.include_action_items = True
        prompt = get_prompt_for_category(TaskCategory.TEXT_DOCS, preferences=prefs)
        assert "Задачи и шаги" in prompt
        assert "Список задач (Action Items)" in prompt

    def test_prompt_with_bullets_format(self) -> None:
        prefs = UserPreferences.default_for_user(1)
        prefs.format = OutputFormat.BULLETS
        prompt = get_prompt_for_category(TaskCategory.TEXT_DOCS, preferences=prefs)
        assert "Форматирование: Отвечай только четким маркированным списком" in prompt


class TestSettingsKeyboard:
    """Test inline keyboard structure."""

    def test_settings_keyboard_generation(self) -> None:
        prefs = UserPreferences.default_for_user(1)
        markup = get_settings_keyboard(prefs)
        assert len(markup.inline_keyboard) == 5

        row_texts = [[btn.text for btn in row] for row in markup.inline_keyboard]
        assert any("Язык:" in t for row in row_texts for t in row)
        assert any("Глубина:" in t for row in row_texts for t in row)
        assert any("Формат:" in t for row in row_texts for t in row)
        assert any("Список задач:" in t for row in row_texts for t in row)
        assert any("Сбросить по умолчанию" in t for row in row_texts for t in row)
