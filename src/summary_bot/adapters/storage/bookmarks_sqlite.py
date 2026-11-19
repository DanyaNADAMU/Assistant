"""SQLite-backed persistent repository for user bookmarks and knowledge archive."""

import asyncio
import json
import logging
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from summary_bot.config import settings
from summary_bot.core.models.bookmark import BookmarkItem
from summary_bot.core.ports.bookmarks import BookmarksPort

logger = logging.getLogger(__name__)


class SqliteBookmarksRepository(BookmarksPort):
    """Thread-safe SQLite storage repository for user bookmarks."""

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path or settings.db_path
        self._initialized = False

    def _ensure_dir_and_schema(self) -> None:
        """Create database directory and initialize bookmarks schema synchronously."""
        if self._initialized:
            return

        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA synchronous = NORMAL;")
            conn.execute("PRAGMA busy_timeout = 5000;")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS bookmarks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    context_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    source_url TEXT,
                    summary_text TEXT NOT NULL,
                    takeaways_json TEXT NOT NULL,
                    category TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_bookmarks_user
                ON bookmarks(user_id, created_at DESC);
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_bookmarks_user_ctx
                ON bookmarks(user_id, context_id);
                """
            )
            conn.commit()
        self._initialized = True

    def _row_to_item(self, row: tuple[int, int, str, str, str | None, str, str, str, str]) -> BookmarkItem:
        """Convert database row tuple to BookmarkItem."""
        (
            item_id,
            user_id,
            context_id,
            title,
            source_url,
            summary_text,
            takeaways_json,
            category,
            created_at_str,
        ) = row

        try:
            takeaways = json.loads(takeaways_json)
            if not isinstance(takeaways, list):
                takeaways = []
        except Exception:
            takeaways = []

        try:
            created_at = datetime.fromisoformat(created_at_str)
        except Exception:
            created_at = datetime.now(UTC)

        return BookmarkItem(
            id=item_id,
            user_id=user_id,
            context_id=context_id,
            title=title,
            source_url=source_url,
            summary_text=summary_text,
            takeaways=takeaways,
            category=category,
            created_at=created_at,
        )

    def _add_sync(self, item: BookmarkItem) -> int:
        self._ensure_dir_and_schema()
        takeaways_json = json.dumps(item.takeaways, ensure_ascii=False)
        created_at_str = item.created_at.isoformat()

        with sqlite3.connect(self._db_path) as conn:
            cursor = conn.cursor()
            # If already exists for user and context, update it
            cursor.execute(
                "SELECT id FROM bookmarks WHERE user_id = ? AND context_id = ?",
                (item.user_id, item.context_id),
            )
            existing = cursor.fetchone()
            if existing:
                item_id = existing[0]
                cursor.execute(
                    """
                    UPDATE bookmarks
                    SET title = ?, source_url = ?, summary_text = ?, takeaways_json = ?, category = ?
                    WHERE id = ?
                    """,
                    (
                        item.title,
                        item.source_url,
                        item.summary_text,
                        takeaways_json,
                        item.category,
                        item_id,
                    ),
                )
                conn.commit()
                return int(item_id)

            cursor.execute(
                """
                INSERT INTO bookmarks (
                    user_id, context_id, title, source_url,
                    summary_text, takeaways_json, category, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item.user_id,
                    item.context_id,
                    item.title,
                    item.source_url,
                    item.summary_text,
                    takeaways_json,
                    item.category,
                    created_at_str,
                ),
            )
            conn.commit()
            return int(cursor.lastrowid or 0)

    async def add_bookmark(self, item: BookmarkItem) -> int:
        return await asyncio.to_thread(self._add_sync, item)

    def _remove_sync(self, user_id: int, bookmark_id: int) -> bool:
        self._ensure_dir_and_schema()
        with sqlite3.connect(self._db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM bookmarks WHERE id = ? AND user_id = ?",
                (bookmark_id, user_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    async def remove_bookmark(self, user_id: int, bookmark_id: int) -> bool:
        return await asyncio.to_thread(self._remove_sync, user_id, bookmark_id)

    def _remove_by_context_sync(self, user_id: int, context_id: str) -> bool:
        self._ensure_dir_and_schema()
        with sqlite3.connect(self._db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM bookmarks WHERE context_id = ? AND user_id = ?",
                (context_id, user_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    async def remove_bookmark_by_context(self, user_id: int, context_id: str) -> bool:
        return await asyncio.to_thread(self._remove_by_context_sync, user_id, context_id)

    def _is_bookmarked_sync(self, user_id: int, context_id: str) -> bool:
        self._ensure_dir_and_schema()
        with sqlite3.connect(self._db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT 1 FROM bookmarks WHERE user_id = ? AND context_id = ? LIMIT 1",
                (user_id, context_id),
            )
            return cursor.fetchone() is not None

    async def is_bookmarked(self, user_id: int, context_id: str) -> bool:
        return await asyncio.to_thread(self._is_bookmarked_sync, user_id, context_id)

    def _get_sync(self, user_id: int, bookmark_id: int) -> BookmarkItem | None:
        self._ensure_dir_and_schema()
        with sqlite3.connect(self._db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, user_id, context_id, title, source_url,
                       summary_text, takeaways_json, category, created_at
                FROM bookmarks
                WHERE id = ? AND user_id = ?
                """,
                (bookmark_id, user_id),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_item(row)

    async def get_bookmark(self, user_id: int, bookmark_id: int) -> BookmarkItem | None:
        return await asyncio.to_thread(self._get_sync, user_id, bookmark_id)

    def _list_sync(
        self,
        user_id: int,
        page: int,
        page_size: int,
        query: str | None,
    ) -> tuple[list[BookmarkItem], int]:
        self._ensure_dir_and_schema()
        page = max(1, page)
        offset = (page - 1) * page_size

        with sqlite3.connect(self._db_path) as conn:
            cursor = conn.cursor()

            if query and query.strip():
                pattern = f"%{query.strip()}%"
                cursor.execute(
                    """
                    SELECT COUNT(*) FROM bookmarks
                    WHERE user_id = ? AND (title LIKE ? OR summary_text LIKE ? OR source_url LIKE ?)
                    """,
                    (user_id, pattern, pattern, pattern),
                )
                total_count = int(cursor.fetchone()[0])

                cursor.execute(
                    """
                    SELECT id, user_id, context_id, title, source_url,
                           summary_text, takeaways_json, category, created_at
                    FROM bookmarks
                    WHERE user_id = ? AND (title LIKE ? OR summary_text LIKE ? OR source_url LIKE ?)
                    ORDER BY created_at DESC
                    LIMIT ? OFFSET ?
                    """,
                    (user_id, pattern, pattern, pattern, page_size, offset),
                )
            else:
                cursor.execute(
                    "SELECT COUNT(*) FROM bookmarks WHERE user_id = ?",
                    (user_id,),
                )
                total_count = int(cursor.fetchone()[0])

                cursor.execute(
                    """
                    SELECT id, user_id, context_id, title, source_url,
                           summary_text, takeaways_json, category, created_at
                    FROM bookmarks
                    WHERE user_id = ?
                    ORDER BY created_at DESC
                    LIMIT ? OFFSET ?
                    """,
                    (user_id, page_size, offset),
                )

            rows = cursor.fetchall()
            items = [self._row_to_item(row) for row in rows]
            return items, total_count

    async def list_bookmarks(
        self,
        user_id: int,
        page: int = 1,
        page_size: int = 5,
        query: str | None = None,
    ) -> tuple[list[BookmarkItem], int]:
        return await asyncio.to_thread(self._list_sync, user_id, page, page_size, query)

    def _get_all_sync(self, user_id: int) -> list[BookmarkItem]:
        self._ensure_dir_and_schema()
        with sqlite3.connect(self._db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, user_id, context_id, title, source_url,
                       summary_text, takeaways_json, category, created_at
                FROM bookmarks
                WHERE user_id = ?
                ORDER BY created_at DESC
                """,
                (user_id,),
            )
            rows = cursor.fetchall()
            return [self._row_to_item(row) for row in rows]

    async def get_all_bookmarks(self, user_id: int) -> list[BookmarkItem]:
        return await asyncio.to_thread(self._get_all_sync, user_id)
