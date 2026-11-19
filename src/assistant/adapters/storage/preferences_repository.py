"""SQLite-backed persistent repository for user preferences."""

import asyncio
import logging
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from assistant.config import settings
from assistant.core.models.user_preferences import (
    OutputFormat,
    OutputLanguage,
    SummaryDepth,
    UserPreferences,
)

logger = logging.getLogger(__name__)


class SqlitePreferencesRepository:
    """Thread-safe SQLite storage repository for user preferences."""

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path or settings.db_path
        self._initialized = False

    def _ensure_dir_and_schema(self) -> None:
        """Create database directory and initialize tables and PRAGMAs synchronously."""
        if self._initialized:
            return

        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA synchronous = NORMAL;")
            conn.execute("PRAGMA busy_timeout = 5000;")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS user_preferences (
                    user_id INTEGER PRIMARY KEY,
                    language TEXT NOT NULL DEFAULT 'auto',
                    depth TEXT NOT NULL DEFAULT 'standard',
                    format TEXT NOT NULL DEFAULT 'standard',
                    include_action_items INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_user_preferences_updated
                ON user_preferences(updated_at);
                """
            )
            conn.commit()
        self._initialized = True

    def _get_sync(self, user_id: int) -> UserPreferences:
        self._ensure_dir_and_schema()
        with sqlite3.connect(self._db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT user_id, language, depth, format, include_action_items, created_at, updated_at
                FROM user_preferences
                WHERE user_id = ?;
                """,
                (user_id,),
            )
            row = cursor.fetchone()
            if not row:
                return UserPreferences.default_for_user(user_id)

            try:
                return UserPreferences(
                    user_id=row[0],
                    language=OutputLanguage(row[1]),
                    depth=SummaryDepth(row[2]),
                    format=OutputFormat(row[3]),
                    include_action_items=bool(row[4]),
                    created_at=datetime.fromisoformat(row[5]),
                    updated_at=datetime.fromisoformat(row[6]),
                )
            except Exception as exc:
                logger.warning(
                    "Failed to parse preferences row for user %s: %s. Returning default.",
                    user_id,
                    exc,
                )
                return UserPreferences.default_for_user(user_id)

    def _save_sync(self, prefs: UserPreferences) -> None:
        self._ensure_dir_and_schema()
        now_iso = datetime.now(UTC).isoformat()
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """
                INSERT INTO user_preferences (
                    user_id, language, depth, format, include_action_items, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    language = excluded.language,
                    depth = excluded.depth,
                    format = excluded.format,
                    include_action_items = excluded.include_action_items,
                    updated_at = excluded.updated_at;
                """,
                (
                    prefs.user_id,
                    prefs.language.value,
                    prefs.depth.value,
                    prefs.format.value,
                    1 if prefs.include_action_items else 0,
                    prefs.created_at.isoformat(),
                    now_iso,
                ),
            )
            conn.commit()

    def _reset_sync(self, user_id: int) -> UserPreferences:
        self._ensure_dir_and_schema()
        default_prefs = UserPreferences.default_for_user(user_id)
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("DELETE FROM user_preferences WHERE user_id = ?;", (user_id,))
            conn.commit()
        return default_prefs

    async def get(self, user_id: int) -> UserPreferences:
        """Fetch user preferences asynchronously, returning defaults if not found."""
        return await asyncio.to_thread(self._get_sync, user_id)

    async def save(self, prefs: UserPreferences) -> None:
        """Save or update user preferences asynchronously."""
        await asyncio.to_thread(self._save_sync, prefs)

    async def reset(self, user_id: int) -> UserPreferences:
        """Reset user preferences to defaults asynchronously."""
        return await asyncio.to_thread(self._reset_sync, user_id)


# Global singleton repository instance
preferences_repo = SqlitePreferencesRepository()
