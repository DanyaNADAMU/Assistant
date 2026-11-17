"""Storage adapters package."""

from summary_bot.adapters.storage.preferences_repository import (
    SqlitePreferencesRepository,
    preferences_repo,
)

__all__ = ["SqlitePreferencesRepository", "preferences_repo"]
