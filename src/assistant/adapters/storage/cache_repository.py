"""SQLite-backed persistent repository for response caching and deduplication."""

import asyncio
import contextlib
import json
import logging
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from assistant.config import TaskCategory, settings
from assistant.core.models.result import ProcessingResult
from assistant.core.models.user_preferences import UserPreferences
from assistant.core.ports.cache import CachedSummaryItem, CacheStats, ResponseCachePort

logger = logging.getLogger(__name__)


class SqliteResponseCacheRepository(ResponseCachePort):
    """Thread-safe SQLite storage for response caching and deduplication."""

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path or settings.db_path
        self._initialized = False

    def _ensure_dir_and_schema(self) -> None:
        """Initialize database directory, WAL mode, and tables synchronously."""
        if self._initialized:
            return

        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA synchronous = NORMAL;")
            conn.execute("PRAGMA busy_timeout = 5000;")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS summary_cache (
                    content_hash TEXT NOT NULL,
                    is_pro INTEGER NOT NULL DEFAULT 0,
                    language TEXT NOT NULL,
                    depth TEXT NOT NULL,
                    format TEXT NOT NULL,
                    category TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    transcription TEXT,
                    key_takeaways TEXT NOT NULL,
                    model_used TEXT NOT NULL,
                    tokens_prompt INTEGER,
                    tokens_completion INTEGER,
                    hit_count INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    last_hit_at TEXT,
                    PRIMARY KEY (content_hash, is_pro, language, depth, format)
                );
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_summary_cache_created
                ON summary_cache(created_at);
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS refinement_cache (
                    source_hash TEXT NOT NULL,
                    action TEXT NOT NULL,
                    content TEXT NOT NULL,
                    model_used TEXT NOT NULL,
                    hit_count INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    last_hit_at TEXT,
                    PRIMARY KEY (source_hash, action)
                );
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_refinement_cache_created
                ON refinement_cache(created_at);
                """
            )
            conn.commit()
        self._initialized = True

    def _get_summary_sync(
        self,
        content_hash: str,
        is_pro: bool,
        preferences: UserPreferences | None = None,
    ) -> ProcessingResult | None:
        self._ensure_dir_and_schema()
        prefs = preferences or UserPreferences()
        lang = prefs.language.value
        depth = prefs.depth.value
        fmt = prefs.format.value
        pro_int = 1 if is_pro else 0

        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM summary_cache
                WHERE content_hash = ? AND is_pro = ? AND language = ? AND depth = ? AND format = ?;
                """,
                (content_hash, pro_int, lang, depth, fmt),
            )
            row = cursor.fetchone()
            if not row:
                return None

            # Register cache hit
            now = datetime.now(UTC).isoformat()
            cursor.execute(
                """
                UPDATE summary_cache
                SET hit_count = hit_count + 1, last_hit_at = ?
                WHERE content_hash = ? AND is_pro = ? AND language = ? AND depth = ? AND format = ?;
                """,
                (now, content_hash, pro_int, lang, depth, fmt),
            )
            conn.commit()

            takeaways = []
            with contextlib.suppress(Exception):
                takeaways = json.loads(row["key_takeaways"])

            category = TaskCategory.TEXT_DOCS
            with contextlib.suppress(Exception):
                category = TaskCategory(row["category"])

            return ProcessingResult(
                category=category,
                summary=row["summary"],
                transcription=row["transcription"],
                key_takeaways=takeaways,
                model_used=row["model_used"],
                tokens_prompt=row["tokens_prompt"],
                tokens_completion=row["tokens_completion"],
                from_cache=True,
            )

    async def get_summary(
        self,
        content_hash: str,
        is_pro: bool,
        preferences: UserPreferences | None = None,
    ) -> ProcessingResult | None:
        return await asyncio.to_thread(self._get_summary_sync, content_hash, is_pro, preferences)

    def _put_summary_sync(
        self,
        content_hash: str,
        is_pro: bool,
        result: ProcessingResult,
        preferences: UserPreferences | None = None,
    ) -> None:
        self._ensure_dir_and_schema()
        prefs = preferences or UserPreferences()
        lang = prefs.language.value
        depth = prefs.depth.value
        fmt = prefs.format.value
        pro_int = 1 if is_pro else 0
        now = datetime.now(UTC).isoformat()
        takeaways_json = json.dumps(result.key_takeaways, ensure_ascii=False)

        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """
                INSERT INTO summary_cache (
                    content_hash, is_pro, language, depth, format,
                    category, summary, transcription, key_takeaways,
                    model_used, tokens_prompt, tokens_completion,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(content_hash, is_pro, language, depth, format) DO UPDATE SET
                    category = excluded.category,
                    summary = excluded.summary,
                    transcription = excluded.transcription,
                    key_takeaways = excluded.key_takeaways,
                    model_used = excluded.model_used,
                    tokens_prompt = excluded.tokens_prompt,
                    tokens_completion = excluded.tokens_completion;
                """,
                (
                    content_hash,
                    pro_int,
                    lang,
                    depth,
                    fmt,
                    result.category.value,
                    result.summary,
                    result.transcription,
                    takeaways_json,
                    result.model_used,
                    result.tokens_prompt,
                    result.tokens_completion,
                    now,
                ),
            )
            conn.commit()

    async def put_summary(
        self,
        content_hash: str,
        is_pro: bool,
        result: ProcessingResult,
        preferences: UserPreferences | None = None,
    ) -> None:
        await asyncio.to_thread(self._put_summary_sync, content_hash, is_pro, result, preferences)

    def _get_refinement_sync(self, source_hash: str, action: str) -> str | None:
        self._ensure_dir_and_schema()
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT content FROM refinement_cache
                WHERE source_hash = ? AND action = ?;
                """,
                (source_hash, action),
            )
            row = cursor.fetchone()
            if not row:
                return None

            now = datetime.now(UTC).isoformat()
            cursor.execute(
                """
                UPDATE refinement_cache
                SET hit_count = hit_count + 1, last_hit_at = ?
                WHERE source_hash = ? AND action = ?;
                """,
                (now, source_hash, action),
            )
            conn.commit()
            return str(row["content"])

    async def get_refinement(self, source_hash: str, action: str) -> str | None:
        return await asyncio.to_thread(self._get_refinement_sync, source_hash, action)

    def _put_refinement_sync(
        self,
        source_hash: str,
        action: str,
        content: str,
        model_used: str = "",
    ) -> None:
        self._ensure_dir_and_schema()
        now = datetime.now(UTC).isoformat()
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """
                INSERT INTO refinement_cache (
                    source_hash, action, content, model_used, created_at
                )
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(source_hash, action) DO UPDATE SET
                    content = excluded.content,
                    model_used = excluded.model_used;
                """,
                (source_hash, action, content, model_used, now),
            )
            conn.commit()

    async def put_refinement(
        self,
        source_hash: str,
        action: str,
        content: str,
        model_used: str = "",
    ) -> None:
        await asyncio.to_thread(self._put_refinement_sync, source_hash, action, content, model_used)

    def _get_stats_sync(self) -> CacheStats:
        self._ensure_dir_and_schema()
        with sqlite3.connect(self._db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*), COALESCE(SUM(hit_count), 0) FROM summary_cache;")
            row_summary = cursor.fetchone()
            sum_count = row_summary[0] if row_summary else 0
            sum_hits = row_summary[1] if row_summary else 0

            cursor.execute("SELECT COUNT(*), COALESCE(SUM(hit_count), 0) FROM refinement_cache;")
            row_refine = cursor.fetchone()
            ref_count = row_refine[0] if row_refine else 0
            ref_hits = row_refine[1] if row_refine else 0

            return CacheStats(
                summary_count=sum_count,
                summary_hits=sum_hits,
                refinement_count=ref_count,
                refinement_hits=ref_hits,
            )

    async def get_stats(self) -> CacheStats:
        return await asyncio.to_thread(self._get_stats_sync)

    def _search_summaries_sync(
        self,
        query: str = "",
        limit: int = 10,
    ) -> list[CachedSummaryItem]:
        self._ensure_dir_and_schema()
        clean_limit = max(1, min(limit, 50))
        clean_query = query.strip()

        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            if clean_query:
                cursor.execute(
                    """
                    SELECT content_hash, category, summary, key_takeaways,
                           model_used, hit_count, created_at, language, depth, format
                    FROM summary_cache
                    WHERE summary LIKE '%' || ? || '%'
                       OR key_takeaways LIKE '%' || ? || '%'
                       OR content_hash LIKE '%' || ? || '%'
                    ORDER BY created_at DESC
                    LIMIT ?;
                    """,
                    (clean_query, clean_query, clean_query, clean_limit),
                )
            else:
                cursor.execute(
                    """
                    SELECT content_hash, category, summary, key_takeaways,
                           model_used, hit_count, created_at, language, depth, format
                    FROM summary_cache
                    ORDER BY created_at DESC
                    LIMIT ?;
                    """,
                    (clean_limit,),
                )

            rows = cursor.fetchall()
            results: list[CachedSummaryItem] = []
            for row in rows:
                try:
                    takeaways = json.loads(row["key_takeaways"]) if row["key_takeaways"] else []
                    if not isinstance(takeaways, list):
                        takeaways = [str(takeaways)]
                except Exception:
                    takeaways = []

                results.append(
                    CachedSummaryItem(
                        content_hash=str(row["content_hash"]),
                        category=str(row["category"]),
                        summary=str(row["summary"]),
                        key_takeaways=[str(t) for t in takeaways],
                        model_used=str(row["model_used"]),
                        hit_count=int(row["hit_count"]),
                        created_at=str(row["created_at"]),
                        language=str(row["language"]),
                        depth=str(row["depth"]),
                        format=str(row["format"]),
                    )
                )
            return results

    async def search_summaries(
        self,
        query: str = "",
        limit: int = 10,
    ) -> list[CachedSummaryItem]:
        """Search cached summaries by query substring or retrieve recent ones."""
        return await asyncio.to_thread(self._search_summaries_sync, query, limit)


# Singleton instance shared across the application runtime
response_cache = SqliteResponseCacheRepository()
