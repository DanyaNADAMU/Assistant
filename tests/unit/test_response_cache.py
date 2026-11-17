"""Unit tests for SHA-256 persistent response caching and content deduplication."""

from pathlib import Path

import pytest

from summary_bot.adapters.storage.cache_repository import SqliteResponseCacheRepository
from summary_bot.config import Settings, TaskCategory
from summary_bot.core.models.payload import InputPayload, PayloadKind
from summary_bot.core.models.result import ProcessingResult
from summary_bot.core.models.user_preferences import (
    OutputFormat,
    OutputLanguage,
    SummaryDepth,
    UserPreferences,
)
from summary_bot.core.services.runner import ResilientModelRunner


class SpyGateway:
    """Mock gateway that tracks execution counts."""

    def __init__(self) -> None:
        self.call_count = 0
        self.last_model: str = ""

    async def execute(
        self,
        payload: InputPayload,
        model: str,
        system_prompt: str,
    ) -> ProcessingResult:
        _ = payload
        _ = system_prompt
        self.call_count += 1
        self.last_model = model
        return ProcessingResult(
            category=TaskCategory.TEXT_DOCS,
            summary=f"Processed summary {self.call_count}",
            key_takeaways=["Point 1", "Point 2"],
            model_used=model,
        )


def test_payload_content_hash_determinism(tmp_path: Path) -> None:
    """Verify that different input payloads produce stable deterministic hashes."""
    # Text
    p1 = InputPayload(kind=PayloadKind.TEXT, text="Hello world!  ")
    p2 = InputPayload(kind=PayloadKind.TEXT, text="Hello world!")
    assert p1.compute_content_hash() == p2.compute_content_hash()

    # URL
    u1 = InputPayload(kind=PayloadKind.URL, url="https://example.com/article  ")
    u2 = InputPayload(kind=PayloadKind.URL, url="https://example.com/article")
    assert u1.compute_content_hash() == u2.compute_content_hash()
    assert u1.compute_content_hash() != p1.compute_content_hash()

    # File on disk vs in-memory bytes
    content = b"Binary audio or pdf byte sequence 123456"
    test_file = tmp_path / "sample.bin"
    test_file.write_bytes(content)

    pf = InputPayload(kind=PayloadKind.AUDIO, file_path=test_file)
    pb = InputPayload(kind=PayloadKind.AUDIO, content_bytes=content)
    assert pf.compute_content_hash() == pb.compute_content_hash()


@pytest.mark.asyncio
async def test_cache_miss_and_put_summary(tmp_path: Path) -> None:
    """Verify cache miss followed by put and subsequent hit with counter tracking."""
    db_file = tmp_path / "test_cache.db"
    cache = SqliteResponseCacheRepository(db_path=db_file)

    h = "test_hash_123456"
    miss = await cache.get_summary(content_hash=h, is_pro=False)
    assert miss is None

    result = ProcessingResult(
        category=TaskCategory.AUDIO_VIDEO,
        summary="Audio note summary",
        transcription="Hello voice message",
        key_takeaways=["Idea A", "Idea B"],
        model_used="google/gemini-2.0-flash-001",
        tokens_prompt=120,
        tokens_completion=45,
    )

    await cache.put_summary(content_hash=h, is_pro=False, result=result)

    hit = await cache.get_summary(content_hash=h, is_pro=False)
    assert hit is not None
    assert hit.from_cache is True
    assert hit.summary == "Audio note summary"
    assert hit.transcription == "Hello voice message"
    assert hit.key_takeaways == ["Idea A", "Idea B"]
    assert hit.model_used == "google/gemini-2.0-flash-001"
    assert hit.tokens_prompt == 120

    # Second hit increments counter
    hit2 = await cache.get_summary(content_hash=h, is_pro=False)
    assert hit2 is not None

    stats = await cache.get_stats()
    assert stats.summary_count == 1
    assert stats.summary_hits == 2


@pytest.mark.asyncio
async def test_cache_different_preferences_isolation(tmp_path: Path) -> None:
    """Verify that different user preferences isolate cached results."""
    db_file = tmp_path / "test_cache.db"
    cache = SqliteResponseCacheRepository(db_path=db_file)
    h = "common_article_hash"

    pref_ru = UserPreferences(
        language=OutputLanguage.RU,
        depth=SummaryDepth.STANDARD,
        format=OutputFormat.STANDARD,
    )
    pref_en = UserPreferences(
        language=OutputLanguage.EN,
        depth=SummaryDepth.CONCISE,
        format=OutputFormat.BULLETS,
    )

    res_ru = ProcessingResult(
        category=TaskCategory.TEXT_DOCS,
        summary="Русское саммари",
        model_used="model-ru",
    )
    res_en = ProcessingResult(
        category=TaskCategory.TEXT_DOCS,
        summary="English concise summary",
        model_used="model-en",
    )

    await cache.put_summary(content_hash=h, is_pro=False, result=res_ru, preferences=pref_ru)
    await cache.put_summary(content_hash=h, is_pro=False, result=res_en, preferences=pref_en)

    hit_ru = await cache.get_summary(content_hash=h, is_pro=False, preferences=pref_ru)
    hit_en = await cache.get_summary(content_hash=h, is_pro=False, preferences=pref_en)

    assert hit_ru is not None and hit_ru.summary == "Русское саммари"
    assert hit_en is not None and hit_en.summary == "English concise summary"

    # Standard vs Pro isolation
    hit_pro = await cache.get_summary(content_hash=h, is_pro=True, preferences=pref_ru)
    assert hit_pro is None


@pytest.mark.asyncio
async def test_refinement_caching(tmp_path: Path) -> None:
    """Verify secondary refinement action views are cached and tracked."""
    db_file = tmp_path / "test_cache.db"
    cache = SqliteResponseCacheRepository(db_path=db_file)

    source_hash = "source_hash_9876"
    assert await cache.get_refinement(source_hash, "tldr") is None

    await cache.put_refinement(
        source_hash=source_hash,
        action="tldr",
        content="Ultra short punchline",
        model_used="test-model",
    )

    cached_tldr = await cache.get_refinement(source_hash, "tldr")
    assert cached_tldr == "Ultra short punchline"

    # Action isolation
    assert await cache.get_refinement(source_hash, "deep") is None


@pytest.mark.asyncio
async def test_runner_response_cache_integration(tmp_path: Path) -> None:
    """Verify ResilientModelRunner leverages cache to bypass LLM calls."""
    db_file = tmp_path / "runner_cache.db"
    cache = SqliteResponseCacheRepository(db_path=db_file)
    gateway = SpyGateway()
    settings = Settings()

    runner = ResilientModelRunner(gateway=gateway, settings=settings, cache=cache)

    payload = InputPayload(kind=PayloadKind.TEXT, text="Repeated article text about AI agents.")

    # Run 1: Cache Miss -> Gateway called once
    res1 = await runner.run(payload)
    assert res1.from_cache is False
    assert gateway.call_count == 1
    assert "Processed summary 1" in res1.summary

    # Run 2: Cache Hit -> Gateway NOT called!
    res2 = await runner.run(payload)
    assert res2.from_cache is True
    assert gateway.call_count == 1
    assert "Processed summary 1" in res2.summary

    # Run 3: Force Refresh -> Gateway called again, updating cache
    payload_refresh = InputPayload(
        kind=PayloadKind.TEXT,
        text="Repeated article text about AI agents.",
        force_refresh=True,
    )
    res3 = await runner.run(payload_refresh)
    assert res3.from_cache is False
    assert gateway.call_count == 2
    assert "Processed summary 2" in res3.summary

    # Run 4: Regular run now returns the updated cache
    res4 = await runner.run(payload)
    assert res4.from_cache is True
    assert gateway.call_count == 2
    assert "Processed summary 2" in res4.summary


@pytest.mark.asyncio
async def test_runner_refine_caching(tmp_path: Path) -> None:
    """Verify runner.refine leverages persistent cache across calls."""
    db_file = tmp_path / "refine_cache.db"
    cache = SqliteResponseCacheRepository(db_path=db_file)
    gateway = SpyGateway()
    settings = Settings()

    runner = ResilientModelRunner(gateway=gateway, settings=settings, cache=cache)

    # First refinement call -> Gateway called
    ref1 = await runner.refine(source_content="Source document text", action="tldr")
    assert gateway.call_count == 1
    assert "Processed summary 1" in ref1

    # Second refinement call -> Gateway bypassed!
    ref2 = await runner.refine(source_content="Source document text", action="tldr")
    assert gateway.call_count == 1
    assert ref2 == ref1
