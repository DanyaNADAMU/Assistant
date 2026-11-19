"""Media generation orchestrator with model failover."""

import logging
import time
import uuid
from pathlib import Path

from assistant.config import Settings
from assistant.core.models.generated import (
    GeneratedMedia,
    GeneratedMediaError,
    GeneratedMediaResult,
)
from assistant.core.models.intent import RequestIntent
from assistant.core.ports.media_generation import MediaGenerationPort

logger = logging.getLogger(__name__)


class MediaGenerator:
    """Orchestrates image/video generation, failing over primary→fallback model."""

    def __init__(self, venice: MediaGenerationPort, settings: Settings) -> None:
        self._venice = venice
        self._settings = settings

    async def generate_image(
        self,
        prompt: str,
        *,
        output_path: Path | None = None,
    ) -> GeneratedMediaResult:
        """Generate an image, falling back to an alternate model on failure."""
        model = self._settings.gen_image_model
        return await self._generate_with_failover(
            kind=RequestIntent.GENERATE_IMAGE,
            prompt=prompt,
            primary_model=model,
            fallback_model=self._settings.gen_image_model_photoreal,
            output_path=output_path,
        )

    async def generate_video(
        self,
        prompt: str,
        *,
        from_image_bytes: bytes | None = None,
        from_image_mime: str | None = None,
        output_path: Path | None = None,
        duration: str | None = None,
        resolution: str | None = None,
    ) -> GeneratedMediaResult:
        """Generate a video (text-to-video or image-to-video) with failover."""
        primary = (
            self._settings.gen_video_image_model
            if from_image_bytes is not None
            else self._settings.gen_video_text_model
        )
        fallback = (
            self._settings.gen_video_text_model
            if from_image_bytes is not None
            else self._settings.gen_video_image_model
        )
        return await self._generate_video_with_failover(
            prompt=prompt,
            primary_model=primary,
            fallback_model=fallback,
            from_image_bytes=from_image_bytes,
            from_image_mime=from_image_mime,
            output_path=output_path,
            duration=duration or self._settings.gen_video_duration,
            resolution=resolution or self._settings.gen_video_resolution,
        )

    async def _generate_with_failover(
        self,
        *,
        kind: RequestIntent,
        prompt: str,
        primary_model: str,
        fallback_model: str,
        output_path: Path | None,
    ) -> GeneratedMediaResult:
        for attempt, model in enumerate((primary_model, fallback_model)):
            try:
                started = time.perf_counter()
                media = await self._generate_one(kind, prompt, model)
                media.elapsed_seconds = time.perf_counter() - started
                return self._finalize(media, output_path=output_path)
            except GeneratedMediaError as exc:
                logger.warning(
                    "Media generation failed on model '%s' (attempt %d): %s",
                    model,
                    attempt,
                    exc,
                )
                if attempt == 1:  # last model in the list
                    raise

        raise GeneratedMediaError(status_code=500, message="No generation model available")

    async def _generate_video_with_failover(
        self,
        *,
        prompt: str,
        primary_model: str,
        fallback_model: str,
        from_image_bytes: bytes | None,
        from_image_mime: str | None,
        output_path: Path | None,
        duration: str,
        resolution: str,
    ) -> GeneratedMediaResult:
        for attempt, model in enumerate((primary_model, fallback_model)):
            try:
                started = time.perf_counter()
                media = await self._venice.generate_video(
                    prompt,
                    model=model,
                    from_image_bytes=from_image_bytes,
                    from_image_mime=from_image_mime,
                    duration=duration,
                    resolution=resolution,
                    aspect_ratio=self._settings.gen_video_aspect_ratio,
                    negative_prompt=self._settings.gen_video_negative_prompt,
                )
                media.elapsed_seconds = time.perf_counter() - started
                return self._finalize(media, output_path=output_path)
            except GeneratedMediaError as exc:
                logger.warning(
                    "Video generation failed on model '%s' (attempt %d): %s",
                    model,
                    attempt,
                    exc,
                )
                if attempt == 1:
                    raise

        raise GeneratedMediaError(status_code=500, message="No video generation model available")

    async def _generate_one(self, kind: RequestIntent, prompt: str, model: str) -> GeneratedMedia:
        if kind == RequestIntent.GENERATE_IMAGE:
            return await self._venice.generate_image(
                prompt,
                model=model,
                negative_prompt=self._settings.gen_image_negative_prompt,
                width=self._settings.gen_image_width,
                height=self._settings.gen_image_height,
                format=self._settings.gen_image_format,
            )
        raise ValueError(f"Unsupported generation kind for image path: {kind}")

    def _finalize(self, media: GeneratedMedia, *, output_path: Path | None) -> GeneratedMediaResult:
        if output_path is not None:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            media.to_file(output_path)
        return GeneratedMediaResult(
            media=media,
            file_path=output_path,
        )

    @staticmethod
    def default_filename(media: GeneratedMedia) -> str:
        """Produce a deterministic unique filename for the generated artifact."""
        ext = media.default_extension
        return f"generated-{uuid.uuid4().hex[:12]}.{ext}"
