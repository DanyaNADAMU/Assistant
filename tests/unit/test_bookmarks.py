"""Unit tests for the bookmarks and personal knowledge archive subsystem."""

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from summary_bot.adapters.storage.bookmarks_sqlite import SqliteBookmarksRepository
from summary_bot.config import TaskCategory
from summary_bot.core.models.bookmark import BookmarkItem
from summary_bot.core.services.context_store import SummaryContext, context_store
from summary_bot.interfaces.telegram.handlers.bookmarks import (
    handle_bookmark_close,
    handle_bookmark_delete,
    handle_bookmark_export,
    handle_bookmark_open,
    handle_bookmark_page,
    handle_bookmark_toggle,
    handle_saved_command,
)


@pytest.fixture
def temp_db(tmp_path: Path) -> Path:
    """Fixture providing temporary SQLite DB path."""
    return tmp_path / "test_bookmarks.db"


@pytest.fixture
def repo(temp_db: Path) -> SqliteBookmarksRepository:
    """Fixture providing initialized SqliteBookmarksRepository."""
    return SqliteBookmarksRepository(db_path=temp_db)


@pytest.mark.asyncio
async def test_bookmark_item_formatting() -> None:
    """Test BookmarkItem preview and full format rendering."""
    item = BookmarkItem(
        id=1,
        user_id=123,
        context_id="ctx12345",
        title="Test Article Title",
        source_url="https://example.com/article",
        summary_text="This is a summary of the article describing key points.",
        takeaways=["Point 1", "Point 2"],
        category="text_docs",
        created_at=datetime(2026, 11, 17, 12, 0, 0, tzinfo=UTC),
    )

    preview = item.format_preview(index=1)
    assert "**1. Test Article Title**" in preview
    assert "https://example.com/article" in preview
    assert "17.11.2026" in preview
    assert "This is a summary" in preview

    full = item.format_full()
    assert "⭐ **Test Article Title**" in full
    assert "🔗 **Источник:** https://example.com/article" in full
    assert "💡 **Главные мысли:**" in full
    assert "• Point 1" in full
    assert "• Point 2" in full


@pytest.mark.asyncio
async def test_bookmarks_repository_crud(repo: SqliteBookmarksRepository) -> None:
    """Test full CRUD lifecycle in SqliteBookmarksRepository."""
    user_id = 999
    item = BookmarkItem(
        user_id=user_id,
        context_id="ctx1",
        title="Python Guide",
        source_url="https://python.org",
        summary_text="Python programming language notes.",
        takeaways=["Fast", "Clean"],
        category="docs",
    )

    # 1. Add
    b_id = await repo.add_bookmark(item)
    assert b_id > 0
    assert await repo.is_bookmarked(user_id, "ctx1") is True
    assert await repo.is_bookmarked(user_id, "ctx2") is False

    # 2. Get
    fetched = await repo.get_bookmark(user_id, b_id)
    assert fetched is not None
    assert fetched.title == "Python Guide"
    assert fetched.takeaways == ["Fast", "Clean"]

    # 3. Idempotent re-add / update
    item2 = BookmarkItem(
        user_id=user_id,
        context_id="ctx1",
        title="Updated Python Guide",
        source_url="https://python.org",
        summary_text="Updated text.",
        takeaways=["Modern"],
        category="docs",
    )
    b_id2 = await repo.add_bookmark(item2)
    assert b_id2 == b_id
    updated = await repo.get_bookmark(user_id, b_id)
    assert updated is not None
    assert updated.title == "Updated Python Guide"

    # 4. Remove by context
    assert await repo.remove_bookmark_by_context(user_id, "ctx1") is True
    assert await repo.is_bookmarked(user_id, "ctx1") is False
    assert await repo.get_bookmark(user_id, b_id) is None


@pytest.mark.asyncio
async def test_bookmarks_pagination_and_search(repo: SqliteBookmarksRepository) -> None:
    """Test pagination offsets and keyword searching."""
    user_id = 888
    for i in range(1, 11):
        await repo.add_bookmark(
            BookmarkItem(
                user_id=user_id,
                context_id=f"ctx_{i}",
                title=f"Article {i} about {'AI' if i % 2 == 0 else 'Economics'}",
                source_url=f"https://example.com/{i}",
                summary_text=f"Summary text content for number {i}",
                takeaways=[f"Takeaway {i}"],
                category="text",
            )
        )

    # Page 1 (size 4)
    items_p1, total = await repo.list_bookmarks(user_id=user_id, page=1, page_size=4)
    assert total == 10
    assert len(items_p1) == 4

    # Page 3 (size 4 -> items 9, 10)
    items_p3, total3 = await repo.list_bookmarks(user_id=user_id, page=3, page_size=4)
    assert total3 == 10
    assert len(items_p3) == 2

    # Search filter "AI" (5 items)
    items_ai, total_ai = await repo.list_bookmarks(user_id=user_id, page=1, page_size=10, query="AI")
    assert total_ai == 5
    assert len(items_ai) == 5
    assert all("AI" in it.title for it in items_ai)

    # All bookmarks for export
    all_items = await repo.get_all_bookmarks(user_id)
    assert len(all_items) == 10


@pytest.mark.asyncio
async def test_telegram_saved_command_empty(monkeypatch: pytest.MonkeyPatch, repo: SqliteBookmarksRepository) -> None:
    """Test /saved command output when repository has no saved bookmarks."""
    from summary_bot.interfaces.telegram.handlers import bookmarks

    monkeypatch.setattr(bookmarks, "bookmarks_repo", repo)

    msg = MagicMock()
    msg.from_user.id = 555
    msg.text = "/saved"
    msg.reply = AsyncMock()

    await handle_saved_command(msg)
    msg.reply.assert_called_once()
    assert "Ваша библиотека закладок пуста" in msg.reply.call_args[0][0]


@pytest.mark.asyncio
async def test_telegram_bookmark_toggle_flow(monkeypatch: pytest.MonkeyPatch, repo: SqliteBookmarksRepository) -> None:
    """Test interactive bookmark toggle on active summary card."""
    from summary_bot.interfaces.telegram.handlers import bookmarks

    monkeypatch.setattr(bookmarks, "bookmarks_repo", repo)

    # Put a context in store
    ctx = SummaryContext.create(
        original_text="Original summary",
        source_content="Source content",
        summary="Test summary text",
        key_takeaways=["Key point 1"],
        category=TaskCategory.TEXT_DOCS,
        title="Test Doc",
        source_url="https://doc.com",
    )
    await context_store.put(ctx)

    mock_msg = MagicMock()
    mock_msg.chat.id = 777
    mock_msg.edit_reply_markup = AsyncMock()

    cb = MagicMock()
    cb.data = f"bm:toggle:{ctx.cid}"
    cb.from_user.id = 777
    cb.message = mock_msg
    cb.answer = AsyncMock()

    # 1. Toggle ON (save)
    await handle_bookmark_toggle(cb)
    assert await repo.is_bookmarked(777, ctx.cid) is True
    cb.answer.assert_called_with("⭐ Сохранено в закладки!")
    mock_msg.edit_reply_markup.assert_called_once()

    # 2. Toggle OFF (remove)
    cb.answer.reset_mock()
    mock_msg.edit_reply_markup.reset_mock()
    await handle_bookmark_toggle(cb)
    assert await repo.is_bookmarked(777, ctx.cid) is False
    cb.answer.assert_called_with("🗑️ Удалено из закладок")
    mock_msg.edit_reply_markup.assert_called_once()


@pytest.mark.asyncio
async def test_telegram_bookmark_detail_and_page_handlers(
    monkeypatch: pytest.MonkeyPatch, repo: SqliteBookmarksRepository
) -> None:
    """Test opening, navigating, and deleting bookmarks."""
    from summary_bot.interfaces.telegram.handlers import bookmarks

    monkeypatch.setattr(bookmarks, "bookmarks_repo", repo)

    user_id = 666
    b_id = await repo.add_bookmark(
        BookmarkItem(
            user_id=user_id,
            context_id="ctx_nav",
            title="Interactive Nav Article",
            summary_text="Article details",
            takeaways=["T1"],
        )
    )

    mock_msg = MagicMock()
    mock_msg.chat.id = user_id
    mock_msg.edit_text = AsyncMock()

    # 1. Open bookmark
    cb_open = MagicMock()
    cb_open.data = f"bm:open:{b_id}:1"
    cb_open.from_user.id = user_id
    cb_open.message = mock_msg
    cb_open.answer = AsyncMock()
    await handle_bookmark_open(cb_open)
    mock_msg.edit_text.assert_called_once()
    assert "Interactive Nav Article" in mock_msg.edit_text.call_args[0][0]

    # 2. Page navigation
    mock_msg.edit_text.reset_mock()
    cb_page = MagicMock()
    cb_page.data = "bm:page:1"
    cb_page.from_user.id = user_id
    cb_page.message = mock_msg
    cb_page.answer = AsyncMock()
    await handle_bookmark_page(cb_page)
    mock_msg.edit_text.assert_called_once()

    # 3. Delete bookmark
    mock_msg.edit_text.reset_mock()
    cb_del = MagicMock()
    cb_del.data = f"bm:del:{b_id}:1"
    cb_del.from_user.id = user_id
    cb_del.message = mock_msg
    cb_del.answer = AsyncMock()
    await handle_bookmark_delete(cb_del)
    cb_del.answer.assert_called_with("🗑️ Закладка удалена")
    assert await repo.get_bookmark(user_id, b_id) is None


@pytest.mark.asyncio
async def test_telegram_bookmark_export_and_close(
    monkeypatch: pytest.MonkeyPatch, repo: SqliteBookmarksRepository
) -> None:
    """Test exporting user bookmarks to Markdown file."""
    from summary_bot.interfaces.telegram.handlers import bookmarks

    monkeypatch.setattr(bookmarks, "bookmarks_repo", repo)

    user_id = 444
    await repo.add_bookmark(
        BookmarkItem(
            user_id=user_id,
            context_id="ctx_exp",
            title="Exportable Article",
            summary_text="Detailed summary for markdown export.",
            takeaways=["Takeaway A"],
        )
    )

    mock_msg = MagicMock()
    mock_msg.chat.id = user_id
    mock_msg.answer_document = AsyncMock()
    mock_msg.delete = AsyncMock()

    cb = MagicMock()
    cb.data = "bm:export"
    cb.from_user.id = user_id
    cb.message = mock_msg
    cb.answer = AsyncMock()

    await handle_bookmark_export(cb)
    mock_msg.answer_document.assert_called_once()
    doc_arg = mock_msg.answer_document.call_args.kwargs["document"]
    assert doc_arg.filename.startswith("summarybot_bookmarks_")
    assert b"Exportable Article" in doc_arg.data
    cb.answer.assert_called_with("✅ Экспорт готов!")

    # Close test
    cb_close = MagicMock()
    cb_close.data = "bm:close"
    cb_close.message = mock_msg
    cb_close.answer = AsyncMock()
    await handle_bookmark_close(cb_close)
    mock_msg.delete.assert_called_once()
    cb_close.answer.assert_called_once()
