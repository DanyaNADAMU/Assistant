"""Port definition for AI media generation backends."""

from typing import Protocol, runtime_checkable

from assistant.core.models.generated import GeneratedMedia


@runtime_checkable
class MediaGenerationPort(Protocol):
    """Protocol for generating images and videos (currently Venice.AI)."""

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
        """Generate an image from a text prompt and return the encoded media."""
        ...

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
        """Generate a video from a text prompt (and optionally an image seed)."""
        ...
