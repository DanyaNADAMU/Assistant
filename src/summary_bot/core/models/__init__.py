"""Core domain models exports."""

from summary_bot.core.models.bookmark import BookmarkItem
from summary_bot.core.models.payload import InputPayload, PayloadKind
from summary_bot.core.models.result import ProcessingResult
from summary_bot.core.models.user_preferences import (
    OutputFormat,
    OutputLanguage,
    SummaryDepth,
    UserPreferences,
)

__all__ = [
    "BookmarkItem",
    "InputPayload",
    "OutputFormat",
    "OutputLanguage",
    "PayloadKind",
    "ProcessingResult",
    "SummaryDepth",
    "UserPreferences",
]
