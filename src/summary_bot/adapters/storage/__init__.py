"""Storage adapters package."""

from summary_bot.adapters.storage.bookmarks_sqlite import (
    SqliteBookmarksRepository,
)
from summary_bot.adapters.storage.cache_repository import (
    SqliteResponseCacheRepository,
    response_cache,
)
from summary_bot.adapters.storage.preferences_repository import (
    SqlitePreferencesRepository,
    preferences_repo,
)
from summary_bot.core.ports.cache import CacheStats

bookmarks_repo = SqliteBookmarksRepository()

__all__ = [
    "CacheStats",
    "SqliteBookmarksRepository",
    "SqlitePreferencesRepository",
    "SqliteResponseCacheRepository",
    "bookmarks_repo",
    "preferences_repo",
    "response_cache",
]
