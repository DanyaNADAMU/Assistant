"""Multi-URL batch processing and cross-source synthesis service."""

import asyncio
import logging
import re
import time
from dataclasses import dataclass, field
from urllib.parse import urlparse

from summary_bot.config import Settings, TaskCategory
from summary_bot.core.models.payload import InputPayload, PayloadKind
from summary_bot.core.models.user_preferences import UserPreferences
from summary_bot.core.ports.model_gateway import ModelGatewayPort
from summary_bot.core.services.prompts import get_batch_synthesis_prompt
from summary_bot.core.services.runner import ResilientModelRunner

logger = logging.getLogger(__name__)

URL_REGEX = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
PUNCTUATION_STRIP = ".,!?;:)>]}\"'"
MAX_BATCH_URLS = 5
MAX_CONCURRENT_EXTRACTIONS = 3


def extract_urls(text: str) -> list[str]:
    """Extract and deduplicate HTTP/HTTPS URLs from text, preserving order."""
    if not text:
        return []
    raw_urls = URL_REGEX.findall(text)
    clean_urls: list[str] = []
    seen: set[str] = set()

    for url in raw_urls:
        cleaned = url.rstrip(PUNCTUATION_STRIP)
        if cleaned and cleaned not in seen:
            try:
                parsed = urlparse(cleaned)
                if parsed.scheme in ("http", "https") and parsed.netloc:
                    clean_urls.append(cleaned)
                    seen.add(cleaned)
            except Exception:
                continue

    return clean_urls


@dataclass
class BatchItemResult:
    """Individual summarization result for a single URL in the batch."""

    url: str
    title: str | None = None
    summary: str = ""
    key_takeaways: list[str] = field(default_factory=list)
    category: TaskCategory = TaskCategory.TEXT_DOCS
    model_used: str = ""
    duration_seconds: float = 0.0
    from_cache: bool = False
    error: str | None = None


@dataclass
class BatchSummaryResult:
    """Overarching synthesis and collection of individual batch summaries."""

    items: list[BatchItemResult]
    synthesis: str
    synthesis_model: str
    total_sources: int
    successful_sources: int
    duration_seconds: float
    user_instruction: str | None = None

    def format_telegram_message(self) -> str:
        """Format the multi-URL synthesis and source summaries for Telegram."""
        parts: list[str] = []

        # 1. Header
        header = (
            f"🌐 **Мульти-источниковый аналитический обзор** "
            f"({self.successful_sources}/{self.total_sources} источников)"
        )
        if self.user_instruction:
            header += f"\n🎯 *Фокус анализа: {self.user_instruction.strip()}*"
        parts.append(header + "\n")

        # 2. Cross-Source Synthesis
        if self.synthesis:
            parts.append(self.synthesis.strip() + "\n")

        # 3. Individual Source Overviews
        parts.append("📚 **Обзор отдельных источников**:")
        for idx, item in enumerate(self.items, start=1):
            parsed_host = urlparse(item.url).netloc or item.url
            item_header = f"🔹 **Источник {idx}** ([{parsed_host}]({item.url})):"
            if item.error:
                parts.append(f"{item_header}\n❌ *Ошибка извлечения:* `{item.error}`\n")
            else:
                summary_excerpt = item.summary.strip()
                takeaways = ""
                if item.key_takeaways:
                    takeaways = "\n" + "\n".join(f"  • {t.strip()}" for t in item.key_takeaways)
                cache_tag = " `⚡[кэш]`" if item.from_cache else ""
                parts.append(f"{item_header}{cache_tag}\n{summary_excerpt}{takeaways}\n")

        # 4. Footer
        footer = f"—\n🤖 *Синтез: {self.synthesis_model}* • ⏱ {self.duration_seconds:.2f}s"
        parts.append(footer)

        return "\n".join(parts)


class BatchSummarizer:
    """Orchestrator for concurrent multi-URL summarization and cross-source synthesis."""

    def __init__(
        self,
        runner: ResilientModelRunner,
        gateway: ModelGatewayPort,
        settings: Settings,
        max_batch_urls: int = MAX_BATCH_URLS,
        concurrency: int = MAX_CONCURRENT_EXTRACTIONS,
    ) -> None:
        self._runner = runner
        self._gateway = gateway
        self._settings = settings
        self._max_batch_urls = max_batch_urls
        self._semaphore = asyncio.Semaphore(concurrency)

    async def summarize_batch(
        self,
        urls: list[str],
        user_instruction: str | None = None,
        is_pro: bool = False,
        force_refresh: bool = False,
        preferences: UserPreferences | None = None,
    ) -> BatchSummaryResult:
        """Process multiple URLs concurrently and synthesize an overarching executive summary."""
        start_time = time.perf_counter()
        target_urls = urls[: self._max_batch_urls]

        async def _process_single_url(url: str) -> BatchItemResult:
            async with self._semaphore:
                payload = InputPayload(
                    kind=PayloadKind.URL,
                    url=url,
                    is_pro=is_pro,
                    force_refresh=force_refresh,
                )
                try:
                    result = await self._runner.run(payload, preferences=preferences)
                    return BatchItemResult(
                        url=url,
                        summary=result.summary,
                        key_takeaways=result.key_takeaways,
                        category=result.category,
                        model_used=result.model_used,
                        duration_seconds=result.duration_seconds,
                        from_cache=result.from_cache,
                    )
                except Exception as exc:
                    logger.warning("Batch item processing failed for URL %s: %s", url, exc)
                    return BatchItemResult(
                        url=url,
                        error=str(exc),
                    )

        # Step 1: Concurrently process all URLs
        items: list[BatchItemResult] = await asyncio.gather(
            *[_process_single_url(u) for u in target_urls]
        )

        successful_items = [item for item in items if not item.error]
        successful_count = len(successful_items)

        if not successful_items:
            # All URLs failed
            total_time = time.perf_counter() - start_time
            return BatchSummaryResult(
                items=items,
                synthesis="❌ Не удалось получить содержимое ни по одной из указанных ссылок.",
                synthesis_model="none",
                total_sources=len(target_urls),
                successful_sources=0,
                duration_seconds=total_time,
                user_instruction=user_instruction,
            )

        # Step 2: Build cross-source synthesis prompt
        sources_text_blocks: list[str] = []
        for idx, item in enumerate(successful_items, start=1):
            takeaways_text = (
                "\nКлючевые тезисы:\n" + "\n".join(f"- {t}" for t in item.key_takeaways)
                if item.key_takeaways
                else ""
            )
            sources_text_blocks.append(
                f"### Источник {idx} ({item.url}):\n{item.summary.strip()}{takeaways_text}"
            )

        combined_sources_text = "\n\n".join(sources_text_blocks)
        if user_instruction:
            combined_sources_text += (
                f"\n\nПользовательский запрос/фокус анализа: {user_instruction.strip()}"
            )

        synthesis_prompt = get_batch_synthesis_prompt(preferences=preferences)
        synthesis_category = TaskCategory.PRO if is_pro else TaskCategory.TEXT_DOCS
        primary_model, fallback_model = self._settings.get_models_for_category(synthesis_category)

        synthesis_payload = InputPayload(
            kind=PayloadKind.TEXT,
            text=combined_sources_text,
            is_pro=is_pro,
        )

        try:
            synthesis_result = await self._gateway.execute(
                payload=synthesis_payload,
                model=primary_model,
                system_prompt=synthesis_prompt,
            )
            synthesis_text = synthesis_result.summary
            model_used = primary_model
        except Exception as exc:
            logger.warning(
                "Batch synthesis primary model failed (%s), trying fallback: %s",
                primary_model,
                exc,
            )
            synthesis_result = await self._gateway.execute(
                payload=synthesis_payload,
                model=fallback_model,
                system_prompt=synthesis_prompt,
            )
            synthesis_text = synthesis_result.summary
            model_used = fallback_model

        total_time = time.perf_counter() - start_time
        return BatchSummaryResult(
            items=items,
            synthesis=synthesis_text,
            synthesis_model=model_used,
            total_sources=len(target_urls),
            successful_sources=successful_count,
            duration_seconds=total_time,
            user_instruction=user_instruction,
        )
