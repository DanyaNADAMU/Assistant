"""In-memory bounded context store for interactive message actions."""

import asyncio
import time
import uuid
from dataclasses import dataclass, field

from summary_bot.config import TaskCategory


@dataclass
class SummaryContext:
    """Holds context and cached dynamic views for an interactive summary message."""

    cid: str
    original_text: str
    source_content: str
    summary: str
    transcription: str | None = None
    key_takeaways: list[str] = field(default_factory=list)
    category: TaskCategory = TaskCategory.TEXT_DOCS
    model_used: str = ""
    views: dict[str, str] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    user_id: int | None = None
    title: str = "Саммари материала"
    source_url: str | None = None

    @classmethod
    def create(
        cls,
        original_text: str,
        source_content: str,
        summary: str,
        transcription: str | None = None,
        key_takeaways: list[str] | None = None,
        category: TaskCategory = TaskCategory.TEXT_DOCS,
        model_used: str = "",
        user_id: int | None = None,
        title: str = "Саммари материала",
        source_url: str | None = None,
    ) -> "SummaryContext":
        """Factory creating a new context with a unique 8-character ID."""
        cid = uuid.uuid4().hex[:8]
        return cls(
            cid=cid,
            original_text=original_text,
            source_content=source_content,
            summary=summary,
            transcription=transcription,
            key_takeaways=key_takeaways or [],
            category=category,
            model_used=model_used,
            user_id=user_id,
            title=title,
            source_url=source_url,
        )


class SummaryContextStore:
    """Thread-safe bounded store for summary contexts with LRU eviction."""

    def __init__(self, max_size: int = 2000, ttl_seconds: float = 86400.0) -> None:
        self._max_size = max_size
        self._ttl_seconds = ttl_seconds
        self._store: dict[str, SummaryContext] = {}
        self._lock = asyncio.Lock()

    async def put(self, context: SummaryContext) -> None:
        """Store a context, evicting oldest items when capacity is reached."""
        async with self._lock:
            self._cleanup_expired()
            if len(self._store) >= self._max_size:
                # Evict the oldest item (first key in insertion-ordered dict)
                oldest_key = next(iter(self._store))
                del self._store[oldest_key]
            self._store[context.cid] = context

    async def get(self, cid: str) -> SummaryContext | None:
        """Retrieve context by ID if present and not expired."""
        async with self._lock:
            context = self._store.get(cid)
            if context is None:
                return None
            if time.time() - context.created_at > self._ttl_seconds:
                del self._store[cid]
                return None
            return context

    async def get_latest_for_user(self, user_id: int) -> SummaryContext | None:
        """Retrieve the most recent unexpired context for a given user ID."""
        async with self._lock:
            self._cleanup_expired()
            for context in reversed(self._store.values()):
                if context.user_id == user_id:
                    return context
            return None

    def _cleanup_expired(self) -> None:
        """Remove expired entries."""
        now = time.time()
        expired_keys = [
            cid for cid, ctx in self._store.items() if now - ctx.created_at > self._ttl_seconds
        ]
        for cid in expired_keys:
            del self._store[cid]


# Global shared instance
context_store = SummaryContextStore()
