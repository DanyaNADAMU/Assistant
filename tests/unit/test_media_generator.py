"""Tests for the MediaGenerator orchestration and model failover."""

import asyncio

from assistant.config import Settings
from assistant.core.models.generated import (
    GeneratedMedia,
    GeneratedMediaError,
    GeneratedMediaKind,
)
from assistant.core.services.media_generator import MediaGenerator


class FakeVenice:
    """Configurable fake MediaGenerationPort."""

    def __init__(self, fail_models: set[str], image_bytes: bytes = b"png-bytes") -> None:
        self.fail_models = fail_models
        self.image_bytes = image_bytes
        self.image_calls: list[str] = []
        self.video_calls: list[str] = []

    async def generate_image(
        self,
        prompt: str,
        *,
        model: str,
        negative_prompt: str | None = None,
        width: int | None = None,
        height: int | None = None,
        format: str | None = None,
    ) -> GeneratedMedia:
        _ = negative_prompt, width, height, format
        self.image_calls.append(model)
        if model in self.fail_models:
            raise GeneratedMediaError(status_code=429, message="rate limited")
        return GeneratedMedia(
            kind=GeneratedMediaKind.IMAGE,
            content_bytes=self.image_bytes,
            mime_type="image/png",
            model_used=model,
            prompt=prompt,
        )

    async def generate_video(
        self,
        prompt: str,
        *,
        model: str,
        from_image_bytes: bytes | None = None,
        from_image_mime: str | None = None,
        duration: str | None = None,
        resolution: str | None = None,
        aspect_ratio: str | None = None,
        negative_prompt: str | None = None,
    ) -> GeneratedMedia:
        _ = (
            from_image_bytes,
            from_image_mime,
            duration,
            resolution,
            aspect_ratio,
            negative_prompt,
        )
        self.video_calls.append(model)
        if model in self.fail_models:
            raise GeneratedMediaError(status_code=429, message="rate limited")
        return GeneratedMedia(
            kind=GeneratedMediaKind.VIDEO,
            content_bytes=b"mp4-bytes",
            mime_type="video/mp4",
            model_used=model,
            prompt=prompt,
        )


def test_image_primary_success() -> None:
    async def run() -> None:
        venice = FakeVenice(fail_models=set())
        settings = Settings(VENICE_API_KEY="k")
        generator = MediaGenerator(venice=venice, settings=settings)
        result = await generator.generate_image("a dragon")
        assert result.media.model_used == settings.gen_image_model
        assert venice.image_calls == [settings.gen_image_model]

    asyncio.run(run())


def test_image_failover_to_photoreal() -> None:
    async def run() -> None:
        venice = FakeVenice(fail_models={Settings().gen_image_model})
        settings = Settings(VENICE_API_KEY="k")
        generator = MediaGenerator(venice=venice, settings=settings)
        result = await generator.generate_image("a dragon")
        assert result.media.model_used == settings.gen_image_model_photoreal
        assert venice.image_calls == [settings.gen_image_model, settings.gen_image_model_photoreal]

    asyncio.run(run())


def test_image_output_path_is_written() -> None:
    from pathlib import Path

    async def run() -> None:
        venice = FakeVenice(fail_models=set())
        settings = Settings(VENICE_API_KEY="k")
        generator = MediaGenerator(venice=venice, settings=settings)
        out = Path("/tmp/assistant-test-out.png")
        result = await generator.generate_image("x", output_path=out)
        assert result.file_path == out
        assert out.exists()
        assert out.read_bytes() == b"png-bytes"
        out.unlink(missing_ok=True)

    asyncio.run(run())


def test_video_primary_success() -> None:
    async def run() -> None:
        venice = FakeVenice(fail_models=set())
        settings = Settings(VENICE_API_KEY="k")
        generator = MediaGenerator(venice=venice, settings=settings)
        result = await generator.generate_video("a bird")
        assert result.media.model_used == settings.gen_video_text_model
        assert venice.video_calls == [settings.gen_video_text_model]

    asyncio.run(run())


def test_video_image_to_video_uses_image_model() -> None:
    async def run() -> None:
        venice = FakeVenice(fail_models=set())
        settings = Settings(VENICE_API_KEY="k")
        generator = MediaGenerator(venice=venice, settings=settings)
        result = await generator.generate_video(
            "animate this", from_image_bytes=b"seed", from_image_mime="image/png"
        )
        assert result.media.model_used == settings.gen_video_image_model
        assert venice.video_calls == [settings.gen_video_image_model]

    asyncio.run(run())
