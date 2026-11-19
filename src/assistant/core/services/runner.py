"""Resilient pipeline runner orchestrating extraction, model routing, and failover."""

import hashlib
import logging
import time
from collections.abc import Sequence

from assistant.config import Settings, TaskCategory
from assistant.core.models.payload import InputPayload, PayloadKind
from assistant.core.models.result import ProcessingResult
from assistant.core.models.user_preferences import UserPreferences
from assistant.core.ports.cache import ResponseCachePort
from assistant.core.ports.extractor import MediaExtractorPort
from assistant.core.ports.model_gateway import ModelGatewayPort
from assistant.core.services.detector import CategoryDetector
from assistant.core.services.prompts import get_prompt_for_category, get_refinement_prompt

logger = logging.getLogger(__name__)


class ResilientModelRunner:
    """Core orchestrator executing the ingestion pipeline with automatic failover."""

    def __init__(
        self,
        gateway: ModelGatewayPort,
        settings: Settings,
        extractors: Sequence[MediaExtractorPort] | None = None,
        cache: ResponseCachePort | None = None,
    ) -> None:
        self._gateway = gateway
        self._settings = settings
        self._extractors = list(extractors or [])
        self._cache = cache

    async def run(
        self, payload: InputPayload, preferences: UserPreferences | None = None
    ) -> ProcessingResult:
        """Run payload through extraction, classification, and resilient model execution."""
        start_time = time.perf_counter()
        content_hash = payload.compute_content_hash()

        # Step 0: Check SHA-256 persistent response cache
        if not payload.force_refresh and self._cache is not None:
            try:
                cached = await self._cache.get_summary(
                    content_hash=content_hash,
                    is_pro=payload.is_pro,
                    preferences=preferences,
                )
                if cached is not None:
                    logger.info(
                        "Cache hit for hash %s... [kind=%s] -> returning cached result",
                        content_hash[:8],
                        payload.kind,
                    )
                    cached.from_cache = True
                    cached.duration_seconds = time.perf_counter() - start_time
                    return cached
            except Exception as cache_exc:
                logger.warning("Cache lookup error for hash %s: %s", content_hash[:8], cache_exc)

        # Step 1: Pre-process and enrich payload via registered extractors
        current_payload = payload
        for extractor in self._extractors:
            if await extractor.can_handle(current_payload):
                try:
                    current_payload = await extractor.extract(current_payload)
                except Exception as exc:
                    logger.warning(
                        "Extractor %s failed on payload %s: %s",
                        type(extractor).__name__,
                        payload.kind,
                        exc,
                    )

        # Immediate friendly response for silence-only recordings
        if current_payload.metadata.get("is_silent"):
            logger.info("Payload detected as pure silence; returning immediate friendly response")
            orig_dur = current_payload.metadata.get("original_duration", 0.0)
            return ProcessingResult(
                category=TaskCategory.AUDIO_VIDEO,
                summary="Аудиозапись не содержит слышимой речи (тишина или неразборчивый шум).",
                transcription=None,
                key_takeaways=[],
                model_used="local/vad-silence-filter",
                audio_duration_seconds=orig_dur,
                duration_seconds=time.perf_counter() - start_time,
            )

        # Step 2: Determine task category and appropriate prompt
        category: TaskCategory = CategoryDetector.detect(current_payload)
        system_prompt = get_prompt_for_category(category, preferences=preferences)
        primary_model, fallback_model = self._settings.get_models_for_category(category)

        logger.info(
            "Routing payload [kind=%s] -> Category: %s | Primary: %s | Fallback: %s",
            current_payload.kind,
            category.value,
            primary_model,
            fallback_model,
        )

        result: ProcessingResult | None = None

        # Step 3: Attempt Primary model execution
        try:
            result = await self._gateway.execute(
                payload=current_payload,
                model=primary_model,
                system_prompt=system_prompt,
            )
            result.category = category
            result.used_fallback = False
            result.duration_seconds = time.perf_counter() - start_time
        except Exception as primary_error:
            logger.warning(
                "Primary model '%s' failed for category '%s' with error: %s. Initiating failover to '%s'",
                primary_model,
                category.value,
                primary_error,
                fallback_model,
            )

            # Step 4: Execute Fallback model
            try:
                result = await self._gateway.execute(
                    payload=current_payload,
                    model=fallback_model,
                    system_prompt=system_prompt,
                )
                result.category = category
                result.used_fallback = True
                result.duration_seconds = time.perf_counter() - start_time
            except Exception as fallback_error:
                logger.error(
                    "Both Primary '%s' and Fallback '%s' failed for category '%s'. Fallback error: %s",
                    primary_model,
                    fallback_model,
                    category.value,
                    fallback_error,
                )
                raise fallback_error

        if result is not None:
            if "duration_seconds" in current_payload.metadata:
                result.audio_duration_seconds = float(current_payload.metadata["duration_seconds"])
            elif "original_duration" in current_payload.metadata:
                result.audio_duration_seconds = float(current_payload.metadata["original_duration"])

        # Step 5: Store successful result in persistent cache
        if result is not None and self._cache is not None:
            try:
                await self._cache.put_summary(
                    content_hash=content_hash,
                    is_pro=payload.is_pro,
                    result=result,
                    preferences=preferences,
                )
            except Exception as cache_exc:
                logger.warning("Failed to store summary in cache: %s", cache_exc)

        return result

    async def refine(
        self,
        source_content: str,
        action: str,
        category: TaskCategory = TaskCategory.TEXT_DOCS,
    ) -> str:
        """Execute a secondary refinement action (e.g. TL;DR, action items, deep dive, translation)."""
        source_hash = hashlib.sha256(source_content.strip().encode("utf-8")).hexdigest()

        if self._cache is not None:
            try:
                cached_refine = await self._cache.get_refinement(source_hash, action)
                if cached_refine is not None:
                    logger.info(
                        "Cache hit for refinement '%s' [hash=%s...]",
                        action,
                        source_hash[:8],
                    )
                    return cached_refine
            except Exception as cache_exc:
                logger.warning("Refinement cache lookup error: %s", cache_exc)

        prompt = get_refinement_prompt(action)
        payload = InputPayload(kind=PayloadKind.TEXT, text=source_content)
        primary_model, fallback_model = self._settings.get_models_for_category(category)

        refined_text = ""
        model_used = primary_model
        try:
            result = await self._gateway.execute(
                payload=payload,
                model=primary_model,
                system_prompt=prompt,
            )
            refined_text = result.summary
            model_used = primary_model
        except Exception as primary_error:
            logger.warning(
                "Primary model '%s' failed for refinement '%s': %s. Retrying fallback '%s'",
                primary_model,
                action,
                primary_error,
                fallback_model,
            )
            result = await self._gateway.execute(
                payload=payload,
                model=fallback_model,
                system_prompt=prompt,
            )
            refined_text = result.summary
            model_used = fallback_model

        if self._cache is not None:
            try:
                await self._cache.put_refinement(
                    source_hash=source_hash,
                    action=action,
                    content=refined_text,
                    model_used=model_used,
                )
            except Exception as cache_exc:
                logger.warning("Failed to store refinement in cache: %s", cache_exc)

        return refined_text
