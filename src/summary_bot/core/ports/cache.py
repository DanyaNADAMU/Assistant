"""Core port interface for persistent response caching and deduplication."""

from dataclasses import dataclass
from typing import Protocol

from summary_bot.core.models.result import ProcessingResult
from summary_bot.core.models.user_preferences import UserPreferences


@dataclass(frozen=True)
class CacheStats:
    """Aggregated cache statistics."""

    summary_count: int
    summary_hits: int
    refinement_count: int
    refinement_hits: int

    @property
    def total_entries(self) -> int:
        """Total entries cached across summaries and refinements."""
        return self.summary_count + self.refinement_count

    @property
    def total_hits(self) -> int:
        """Total hits served across summaries and refinements."""
        return self.summary_hits + self.refinement_hits

    @property
    def hit_rate(self) -> float:
        """Cache hit percentage."""
        total_requests = self.total_entries + self.total_hits
        if total_requests == 0:
            return 0.0
        return (self.total_hits / total_requests) * 100.0


class ResponseCachePort(Protocol):
    """Protocol for response caching and deduplication."""

    async def get_summary(
        self,
        content_hash: str,
        is_pro: bool,
        preferences: UserPreferences | None = None,
    ) -> ProcessingResult | None:
        """Retrieve a cached summary result for the content hash and preferences."""
        ...

    async def put_summary(
        self,
        content_hash: str,
        is_pro: bool,
        result: ProcessingResult,
        preferences: UserPreferences | None = None,
    ) -> None:
        """Store a summary result indexed by content hash and preferences."""
        ...

    async def get_refinement(
        self,
        source_hash: str,
        action: str,
    ) -> str | None:
        """Retrieve a cached secondary refinement action view."""
        ...

    async def put_refinement(
        self,
        source_hash: str,
        action: str,
        content: str,
        model_used: str = "",
    ) -> None:
        """Store a secondary refinement action view."""
        ...

    async def get_stats(self) -> CacheStats:
        """Retrieve current cache metrics."""
        ...
