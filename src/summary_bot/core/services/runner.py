"""Resilient pipeline runner orchestrating extraction, model routing, and failover."""

import logging
import time
from collections.abc import Sequence

from summary_bot.config import Settings, TaskCategory
from summary_bot.core.models.payload import InputPayload, PayloadKind
from summary_bot.core.models.result import ProcessingResult
from summary_bot.core.ports.extractor import MediaExtractorPort
from summary_bot.core.ports.model_gateway import ModelGatewayPort
from summary_bot.core.services.detector import CategoryDetector
from summary_bot.core.services.prompts import get_prompt_for_category, get_refinement_prompt

logger = logging.getLogger(__name__)


class ResilientModelRunner:
    """Core orchestrator executing the ingestion pipeline with automatic failover."""

    def __init__(
        self,
        gateway: ModelGatewayPort,
        settings: Settings,
        extractors: Sequence[MediaExtractorPort] | None = None,
    ) -> None:
        self._gateway = gateway
        self._settings = settings
        self._extractors = list(extractors or [])

    async def run(self, payload: InputPayload) -> ProcessingResult:
        """Run payload through extraction, classification, and resilient model execution."""
        start_time = time.perf_counter()

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

        # Step 2: Determine task category and appropriate prompt
        category: TaskCategory = CategoryDetector.detect(current_payload)
        system_prompt = get_prompt_for_category(category)
        primary_model, fallback_model = self._settings.get_models_for_category(category)

        logger.info(
            "Routing payload [kind=%s] -> Category: %s | Primary: %s | Fallback: %s",
            current_payload.kind,
            category.value,
            primary_model,
            fallback_model,
        )

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
            return result
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
            return result
        except Exception as fallback_error:
            logger.error(
                "Both Primary '%s' and Fallback '%s' failed for category '%s'. Fallback error: %s",
                primary_model,
                fallback_model,
                category.value,
                fallback_error,
            )
            raise fallback_error

    async def refine(
        self,
        source_content: str,
        action: str,
        category: TaskCategory = TaskCategory.TEXT_DOCS,
    ) -> str:
        """Execute a secondary refinement action (e.g. TL;DR, action items, deep dive, translation)."""
        prompt = get_refinement_prompt(action)
        payload = InputPayload(kind=PayloadKind.TEXT, text=source_content)
        primary_model, fallback_model = self._settings.get_models_for_category(category)

        try:
            result = await self._gateway.execute(
                payload=payload,
                model=primary_model,
                system_prompt=prompt,
            )
            return result.summary
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
            return result.summary
