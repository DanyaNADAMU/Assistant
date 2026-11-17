"""Unit tests for Multi-URL Batch Processing and Cross-Source Synthesis Suite."""

from unittest.mock import AsyncMock

import pytest

from summary_bot.config import Settings, TaskCategory
from summary_bot.core.models.payload import InputPayload
from summary_bot.core.models.result import ProcessingResult
from summary_bot.core.models.user_preferences import OutputLanguage, SummaryDepth, UserPreferences
from summary_bot.core.ports.model_gateway import ModelGatewayPort
from summary_bot.core.services.batch import (
    BatchSummarizer,
    extract_urls,
)
from summary_bot.core.services.context_store import SummaryContext
from summary_bot.core.services.exporter import DocumentExporter, ExportFormat
from summary_bot.core.services.runner import ResilientModelRunner


def test_extract_urls_various_formats() -> None:
    """Test URL extraction, punctuation stripping, and deduplication."""
    text = (
        "Посмотри эти статьи: https://example.com/one, а также https://example.com/two.\n"
        "Вот еще раз https://example.com/one! И https://test.org/page?id=1&name=test."
    )
    urls = extract_urls(text)
    assert urls == [
        "https://example.com/one",
        "https://example.com/two",
        "https://test.org/page?id=1&name=test",
    ]


def test_extract_urls_empty_or_no_urls() -> None:
    """Test extract_urls with empty or plain text."""
    assert extract_urls("") == []
    assert extract_urls("Привет, как дела? ftp://old-server.com") == []


@pytest.mark.asyncio
async def test_batch_summarize_success() -> None:
    """Test complete batch summarization with multiple successful URLs."""
    runner = AsyncMock(spec=ResilientModelRunner)
    gateway = AsyncMock(spec=ModelGatewayPort)
    settings = Settings(openrouter_api_key="test-key")

    # Mock runner responses for URL 1 and URL 2
    def _mock_run(payload: InputPayload, **_kwargs: object):
        if "alpha" in (payload.url or ""):
            return ProcessingResult(
                category=TaskCategory.TEXT_DOCS,
                summary="Статья Альфа описывает архитектуру микросервисов.",
                key_takeaways=["Слабая связанность", "Независимый деплой"],
                model_used="google/gemini-2.5-flash",
                duration_seconds=0.8,
            )
        return ProcessingResult(
            category=TaskCategory.TEXT_DOCS,
            summary="Статья Бета рассматривает монолитные подходы.",
            key_takeaways=["Простота транзакций", "Быстрый старт"],
            model_used="google/gemini-2.5-flash",
            duration_seconds=0.9,
        )

    runner.run.side_effect = _mock_run

    # Mock gateway synthesis call
    gateway.execute.return_value = ProcessingResult(
        category=TaskCategory.TEXT_DOCS,
        summary=(
            "# 🌐 Сводный синтез\n\n"
            "**Главный сквозной вывод**: Обе статьи исследуют баланс сложности и масштабируемости."
        ),
        model_used="google/gemini-2.5-flash",
        duration_seconds=1.2,
    )

    batch_service = BatchSummarizer(runner=runner, gateway=gateway, settings=settings)
    urls = ["https://news.com/alpha", "https://tech.com/beta"]

    result = await batch_service.summarize_batch(
        urls=urls,
        user_instruction="Сравни компромиссы архитектур",
    )

    assert result.total_sources == 2
    assert result.successful_sources == 2
    assert len(result.items) == 2
    assert result.user_instruction == "Сравни компромиссы архитектур"
    assert "Сводный синтез" in result.synthesis
    assert runner.run.call_count == 2
    assert gateway.execute.call_count == 1

    # Verify formatted telegram message
    formatted = result.format_telegram_message()
    assert "**Мульти-источниковый аналитический обзор** (2/2 источников)" in formatted
    assert "Фокус анализа: Сравни компромиссы архитектур" in formatted
    assert "news.com" in formatted
    assert "tech.com" in formatted
    assert "Статья Альфа" in formatted
    assert "Статья Бета" in formatted


@pytest.mark.asyncio
async def test_batch_summarize_partial_failure() -> None:
    """Test graceful degradation when one URL extraction fails."""
    runner = AsyncMock(spec=ResilientModelRunner)
    gateway = AsyncMock(spec=ModelGatewayPort)
    settings = Settings(openrouter_api_key="test-key")

    def _mock_run(payload: InputPayload, **_kwargs: object):
        if "fail" in (payload.url or ""):
            raise ConnectionError("404 Not Found")
        return ProcessingResult(
            category=TaskCategory.TEXT_DOCS,
            summary="Успешный обзор первого источника.",
            key_takeaways=["Тезис 1"],
            model_used="google/gemini-2.5-flash",
            duration_seconds=0.5,
        )

    runner.run.side_effect = _mock_run
    gateway.execute.return_value = ProcessingResult(
        category=TaskCategory.TEXT_DOCS,
        summary="Синтез по доступным материалам.",
        model_used="google/gemini-2.5-flash",
        duration_seconds=0.6,
    )

    batch_service = BatchSummarizer(runner=runner, gateway=gateway, settings=settings)
    urls = ["https://ok.com/page", "https://fail.com/404"]

    result = await batch_service.summarize_batch(urls=urls)

    assert result.total_sources == 2
    assert result.successful_sources == 1
    assert result.items[0].error is None
    assert result.items[1].error == "404 Not Found"

    formatted = result.format_telegram_message()
    assert "**Мульти-источниковый аналитический обзор** (1/2 источников)" in formatted
    assert "❌ *Ошибка извлечения:* `404 Not Found`" in formatted


@pytest.mark.asyncio
async def test_batch_summarize_all_failed() -> None:
    """Test behavior when all provided URLs fail."""
    runner = AsyncMock(spec=ResilientModelRunner)
    gateway = AsyncMock(spec=ModelGatewayPort)
    settings = Settings(openrouter_api_key="test-key")

    runner.run.side_effect = TimeoutError("Gateway Timeout")

    batch_service = BatchSummarizer(runner=runner, gateway=gateway, settings=settings)
    urls = ["https://down1.com", "https://down2.com"]

    result = await batch_service.summarize_batch(urls=urls)

    assert result.total_sources == 2
    assert result.successful_sources == 0
    assert "Не удалось получить содержимое ни по одной из указанных ссылок" in result.synthesis
    assert gateway.execute.call_count == 0  # Synthesis shouldn't be called if all failed


@pytest.mark.asyncio
async def test_batch_summarize_with_preferences() -> None:
    """Test that user preferences (e.g. English, Concise) are applied to synthesis."""
    runner = AsyncMock(spec=ResilientModelRunner)
    gateway = AsyncMock(spec=ModelGatewayPort)
    settings = Settings(openrouter_api_key="test-key")

    runner.run.return_value = ProcessingResult(
        category=TaskCategory.TEXT_DOCS,
        summary="Article summary",
        model_used="google/gemini-2.5-flash",
    )
    gateway.execute.return_value = ProcessingResult(
        category=TaskCategory.TEXT_DOCS,
        summary="English synthesized overview",
        model_used="google/gemini-2.5-flash",
    )

    prefs = UserPreferences(
        language=OutputLanguage.EN,
        depth=SummaryDepth.CONCISE,
    )

    batch_service = BatchSummarizer(runner=runner, gateway=gateway, settings=settings)
    result = await batch_service.summarize_batch(
        urls=["https://example.com/1", "https://example.com/2"],
        preferences=prefs,
    )

    assert result.successful_sources == 2
    # Verify preferences were passed to gateway synthesis call
    call_args = gateway.execute.call_args
    assert "fluent English" in call_args.kwargs["system_prompt"]
    assert "лаконичен" in call_args.kwargs["system_prompt"]


def test_batch_export_to_all_formats() -> None:
    """Test converting batch summary into document context and exporting to MD, HTML, and TXT."""
    formatted_text = "Мульти-источниковый аналитический обзор..."
    ctx = SummaryContext.create(
        original_text=formatted_text,
        source_content="Синтез и статьи...",
        summary="Кросс-источниковый синтез двух материалов.",
        key_takeaways=["Ключевой вывод A", "Ключевой вывод B"],
        category=TaskCategory.TEXT_DOCS,
        model_used="google/gemini-2.5-flash",
    )

    exporter = DocumentExporter()

    for fmt in (ExportFormat.MARKDOWN, ExportFormat.HTML, ExportFormat.TEXT):
        content_bytes, filename, mime = exporter.export(ctx, fmt, title="Мульти-обзор")
        assert len(content_bytes) > 50
        assert filename.startswith("summary_")
        assert filename.endswith(f".{fmt.value}")
