"""Storage adapters package."""

from summary_bot.adapters.storage.cache_repository import (
    SqliteResponseCacheRepository,
    response_cache,
)
from summary_bot.adapters.storage.preferences_repository import (
    SqlitePreferencesRepository,
    preferences_repo,
)
from summary_bot.core.ports.cache import CacheStats

__all__ = [
    "CacheStats",
    "SqlitePreferencesRepository",
    "SqliteResponseCacheRepository",
    "preferences_repo",
    "response_cache",
]
