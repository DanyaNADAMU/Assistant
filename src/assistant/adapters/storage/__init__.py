"""Storage adapters package."""

from assistant.adapters.storage.cache_repository import (
    SqliteResponseCacheRepository,
    response_cache,
)
from assistant.adapters.storage.preferences_repository import (
    SqlitePreferencesRepository,
    preferences_repo,
)
from assistant.core.ports.cache import CacheStats

__all__ = [
    "CacheStats",
    "SqlitePreferencesRepository",
    "SqliteResponseCacheRepository",
    "preferences_repo",
    "response_cache",
]
