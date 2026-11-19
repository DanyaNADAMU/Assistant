"""Unit tests for Telegram Inline Query mode and cache search functionality."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import InlineQuery, InlineQueryResultArticle, User

from assistant.adapters.storage.cache_repository import SqliteResponseCacheRepository
from assistant.config import Settings, TaskCategory
from assistant.core.models.payload import InputPayload, PayloadKind
from assistant.core.models.result import ProcessingResult
from assistant.core.services.runner import ResilientModelRunner
from assistant.interfaces.telegram.handlers.inline import handle_inline_query


class MockGateway:
    """Mock Gateway for test execution."""

    async def execute(
        self,
        payload: InputPayload,
        model: str,
        system_prompt: str,
    ) -> ProcessingResult:
        _ = payload
        _ = system_prompt
        return ProcessingResult(
            category=TaskCategory.TEXT_DOCS,
            summary="Mock Gateway Summary",
            key_takeaways=["Mock Takeaway 1"],
            model_used=model,
        )


@pytest.fixture
def test_cache(tmp_path: Path) -> SqliteResponseCacheRepository:
    """Provide isolated SQLite cache repository."""
    return SqliteResponseCacheRepository(db_path=tmp_path / "test_inline_cache.sqlite3")


@pytest.fixture
def mock_runner(test_cache: SqliteResponseCacheRepository) -> ResilientModelRunner:
    """Create test runner with mock dependencies."""
    settings = Settings(
        OPENROUTER_API_KEY="test-key",
        TELEGRAM_BOT_TOKEN="123456:ABC-DEF",
    )
    return ResilientModelRunner(
        gateway=MockGateway(),
        settings=settings,
        extractors=[],
        cache=test_cache,
    )


@pytest.mark.asyncio
async def test_cache_search_summaries(test_cache: SqliteResponseCacheRepository) -> None:
    """Verify search_summaries returns recent items and filters by query substring."""
    r1 = ProcessingResult(
        category=TaskCategory.TEXT_DOCS,
        summary="Python asynchronous programming with asyncio",
        key_takeaways=["Event loop", "Coroutines"],
        model_used="google/gemini-flash",
    )
    r2 = ProcessingResult(
        category=TaskCategory.AUDIO_VIDEO,
        summary="Quantum computing algorithms and qubits",
        key_takeaways=["Superposition", "Entanglement"],
        model_used="anthropic/claude-haiku",
    )
    await test_cache.put_summary("hash_python", is_pro=False, result=r1)
    await test_cache.put_summary("hash_quantum", is_pro=False, result=r2)

    # Empty query returns all recent
    all_recent = await test_cache.search_summaries("", limit=5)
    assert len(all_recent) == 2

    # Query matching python
    matches_py = await test_cache.search_summaries("asyncio", limit=5)
    assert len(matches_py) == 1
    assert matches_py[0].content_hash == "hash_python"
    assert "asyncio" in matches_py[0].summary
    assert matches_py[0].key_takeaways == ["Event loop", "Coroutines"]

    # Query matching quantum takeaways
    matches_quantum = await test_cache.search_summaries("Entanglement", limit=5)
    assert len(matches_quantum) == 1
    assert matches_quantum[0].content_hash == "hash_quantum"

    # Non-matching query
    matches_none = await test_cache.search_summaries("SpaceX rockets", limit=5)
    assert len(matches_none) == 0


@pytest.mark.asyncio
async def test_inline_query_empty_returns_recent_and_guide(
    mock_runner: ResilientModelRunner,
    test_cache: SqliteResponseCacheRepository,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify empty query returns recent cached summaries and user guide card."""
    # Populate one summary
    res = ProcessingResult(
        category=TaskCategory.TEXT_DOCS,
        summary="Recent architecture analysis",
        key_takeaways=["Microservices", "CQRS"],
        model_used="google/gemini-flash",
    )
    await test_cache.put_summary("recent_hash", is_pro=False, result=res)
    monkeypatch.setattr(
        "assistant.interfaces.telegram.handlers.inline.response_cache",
        test_cache,
    )

    mock_bot = MagicMock()
    mock_bot.get_me = AsyncMock(
        return_value=User(
            id=123,
            is_bot=True,
            first_name="Assistant",
            username="Assistant",
        )
    )

    inline_query = MagicMock(spec=InlineQuery)
    inline_query.query = ""
    inline_query.bot = mock_bot
    inline_query.answer = AsyncMock()

    await handle_inline_query(inline_query=inline_query, runner=mock_runner)

    assert inline_query.answer.called
    call_args = inline_query.answer.call_args
    results = call_args.kwargs.get("results") or call_args.args[0]
    assert len(results) >= 2
    # First is recent summary, last is usage guide
    assert any(isinstance(r, InlineQueryResultArticle) and "Недавнее" in r.title for r in results)
    assert any(
        isinstance(r, InlineQueryResultArticle) and "Как работает" in r.title for r in results
    )


@pytest.mark.asyncio
async def test_inline_query_cached_url(
    mock_runner: ResilientModelRunner,
    test_cache: SqliteResponseCacheRepository,
) -> None:
    """Verify cached URL query produces instant summary and takeaways articles."""
    url = "https://example.com/deep-dive-ai"
    payload = InputPayload(kind=PayloadKind.URL, url=url)
    content_hash = payload.compute_content_hash()

    res = ProcessingResult(
        category=TaskCategory.TEXT_DOCS,
        summary="Comprehensive breakdown of generative AI models.",
        key_takeaways=["Transformers", "Attention is all you need"],
        model_used="google/gemini-flash",
        from_cache=True,
    )
    await test_cache.put_summary(content_hash, is_pro=False, result=res)

    mock_bot = MagicMock()
    mock_bot.get_me = AsyncMock(
        return_value=User(
            id=123,
            is_bot=True,
            first_name="Assistant",
            username="Assistant",
        )
    )

    inline_query = MagicMock(spec=InlineQuery)
    inline_query.query = f"Check this out: {url}"
    inline_query.bot = mock_bot
    inline_query.answer = AsyncMock()

    await handle_inline_query(inline_query=inline_query, runner=mock_runner)

    assert inline_query.answer.called
    results = inline_query.answer.call_args.kwargs.get("results")
    assert len(results) == 2
    # Result 1: Full summary
    assert "⚡ Саммари" in results[0].title
    assert "Comprehensive breakdown" in results[0].input_message_content.message_text
    # Result 2: Key takeaways
    assert "📋 Главные тезисы" in results[1].title
    assert "Transformers" in results[1].input_message_content.message_text


@pytest.mark.asyncio
async def test_inline_query_uncached_url(
    mock_runner: ResilientModelRunner,
) -> None:
    """Verify uncached URL offers an interactive card to trigger analysis in bot."""
    url = "https://brand-new-site.org/untouched-article"

    mock_bot = MagicMock()
    mock_bot.get_me = AsyncMock(
        return_value=User(
            id=123,
            is_bot=True,
            first_name="Assistant",
            username="Assistant",
        )
    )

    inline_query = MagicMock(spec=InlineQuery)
    inline_query.query = url
    inline_query.bot = mock_bot
    inline_query.answer = AsyncMock()

    await handle_inline_query(inline_query=inline_query, runner=mock_runner)

    assert inline_query.answer.called
    results = inline_query.answer.call_args.kwargs.get("results")
    assert len(results) == 1
    assert "✨ Саммаризировать" in results[0].title
    assert url in results[0].input_message_content.message_text


@pytest.mark.asyncio
async def test_inline_query_search_text(
    mock_runner: ResilientModelRunner,
    test_cache: SqliteResponseCacheRepository,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify keyword queries filter summaries and return empty alert if none found."""
    res = ProcessingResult(
        category=TaskCategory.TEXT_DOCS,
        summary="Kubernetes pod lifecycle and eviction policies",
        key_takeaways=["Kubelet", "Preemption"],
        model_used="google/gemini-flash",
    )
    await test_cache.put_summary("hash_k8s", is_pro=False, result=res)
    monkeypatch.setattr(
        "assistant.interfaces.telegram.handlers.inline.response_cache",
        test_cache,
    )

    mock_bot = MagicMock()
    mock_bot.get_me = AsyncMock(
        return_value=User(
            id=123,
            is_bot=True,
            first_name="Assistant",
            username="Assistant",
        )
    )

    # 1. Search existing keyword
    q_match = MagicMock(spec=InlineQuery)
    q_match.query = "Kubernetes"
    q_match.bot = mock_bot
    q_match.answer = AsyncMock()

    await handle_inline_query(inline_query=q_match, runner=mock_runner)
    results_match = q_match.answer.call_args.kwargs.get("results")
    assert len(results_match) == 1
    assert "Kubernetes pod lifecycle" in results_match[0].input_message_content.message_text

    # 2. Search missing keyword
    q_miss = MagicMock(spec=InlineQuery)
    q_miss.query = "NonExistentWordXYZ"
    q_miss.bot = mock_bot
    q_miss.answer = AsyncMock()

    await handle_inline_query(inline_query=q_miss, runner=mock_runner)
    results_miss = q_miss.answer.call_args.kwargs.get("results")
    assert len(results_miss) == 1
    assert "🔍 Ничего не найдено" in results_miss[0].title
