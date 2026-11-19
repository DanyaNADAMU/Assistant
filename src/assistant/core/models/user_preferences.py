"""Domain models for user preferences and customizable output settings."""

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class OutputLanguage(StrEnum):
    """Preferred output language for summaries."""

    AUTO = "auto"
    RU = "ru"
    EN = "en"

    @property
    def label(self) -> str:
        """Human-readable button/status label."""
        labels = {
            OutputLanguage.AUTO: "⚡ Авто",
            OutputLanguage.RU: "🇷🇺 Русский",
            OutputLanguage.EN: "🇬🇧 English",
        }
        return labels.get(self, self.value)


class SummaryDepth(StrEnum):
    """Desired depth and detail level of generated summaries."""

    CONCISE = "concise"
    STANDARD = "standard"
    DETAILED = "detailed"

    @property
    def label(self) -> str:
        """Human-readable button/status label."""
        labels = {
            SummaryDepth.CONCISE: "⚡ Краткая",
            SummaryDepth.STANDARD: "📄 Стандартная",
            SummaryDepth.DETAILED: "📚 Подробная",
        }
        return labels.get(self, self.value)


class OutputFormat(StrEnum):
    """Preferred structural formatting."""

    STANDARD = "standard"
    BULLETS = "bullets"

    @property
    def label(self) -> str:
        """Human-readable button/status label."""
        labels = {
            OutputFormat.STANDARD: "📑 Тезисы + вывод",
            OutputFormat.BULLETS: "• Только списком",
        }
        return labels.get(self, self.value)


class UserPreferences(BaseModel):
    """Persistent user preferences for summarization styling."""

    user_id: int = 0
    language: OutputLanguage = OutputLanguage.AUTO
    depth: SummaryDepth = SummaryDepth.STANDARD
    format: OutputFormat = OutputFormat.STANDARD
    include_action_items: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def default_for_user(cls, user_id: int) -> "UserPreferences":
        """Generate default preferences for a given user ID."""
        now = datetime.now(UTC)
        return cls(
            user_id=user_id,
            language=OutputLanguage.AUTO,
            depth=SummaryDepth.STANDARD,
            format=OutputFormat.STANDARD,
            include_action_items=False,
            created_at=now,
            updated_at=now,
        )

    def next_language(self) -> OutputLanguage:
        """Cycle to the next language option."""
        cycle = [OutputLanguage.AUTO, OutputLanguage.RU, OutputLanguage.EN]
        idx = cycle.index(self.language)
        return cycle[(idx + 1) % len(cycle)]

    def next_depth(self) -> SummaryDepth:
        """Cycle to the next depth option."""
        cycle = [SummaryDepth.CONCISE, SummaryDepth.STANDARD, SummaryDepth.DETAILED]
        idx = cycle.index(self.depth)
        return cycle[(idx + 1) % len(cycle)]

    def next_format(self) -> OutputFormat:
        """Cycle to the next format option."""
        cycle = [OutputFormat.STANDARD, OutputFormat.BULLETS]
        idx = cycle.index(self.format)
        return cycle[(idx + 1) % len(cycle)]

    def format_settings_card(self, username: str | None = None) -> str:
        """Render a clean Markdown summary card of active user preferences."""
        user_mention = f"@{username}" if username else f"ID: {self.user_id}"
        actions_status = "✅ Включен" if self.include_action_items else "❌ Выключен"

        return (
            "⚙️ **Настройки бота Assistant**\n\n"
            f"👤 **Пользователь**: {user_mention}\n"
            f"🌐 **Язык ответов**: {self.language.label}\n"
            f"📝 **Глубина анализа**: {self.depth.label}\n"
            f"📐 **Форматирование**: {self.format.label}\n"
            f"📋 **Список задач (Action Items)**: {actions_status}\n\n"
            "_Нажимайте на кнопки ниже, чтобы переключать параметры:_"
        )
