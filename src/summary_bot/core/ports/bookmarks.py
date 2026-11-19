"""Abstract port interface for managing user bookmarks and personal archive."""

from abc import ABC, abstractmethod

from summary_bot.core.models.bookmark import BookmarkItem


class BookmarksPort(ABC):
    """Port for persistent bookmark storage operations."""

    @abstractmethod
    async def add_bookmark(self, item: BookmarkItem) -> int:
        """Add a bookmark, returning assigned ID."""
        ...

    @abstractmethod
    async def remove_bookmark(self, user_id: int, bookmark_id: int) -> bool:
        """Remove a bookmark by its primary ID for a user."""
        ...

    @abstractmethod
    async def remove_bookmark_by_context(self, user_id: int, context_id: str) -> bool:
        """Remove a bookmark by context UUID for a user."""
        ...

    @abstractmethod
    async def is_bookmarked(self, user_id: int, context_id: str) -> bool:
        """Check if a specific context is bookmarked by a user."""
        ...

    @abstractmethod
    async def get_bookmark(self, user_id: int, bookmark_id: int) -> BookmarkItem | None:
        """Retrieve a specific bookmark by ID."""
        ...

    @abstractmethod
    async def list_bookmarks(
        self,
        user_id: int,
        page: int = 1,
        page_size: int = 5,
        query: str | None = None,
    ) -> tuple[list[BookmarkItem], int]:
        """List bookmarks with pagination and optional keyword search.

        Returns (items, total_count).
        """
        ...

    @abstractmethod
    async def get_all_bookmarks(self, user_id: int) -> list[BookmarkItem]:
        """Retrieve all bookmarks for a user (for bulk export)."""
        ...
