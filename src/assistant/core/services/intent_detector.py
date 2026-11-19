"""Request intent detection: analysis vs. media generation.

Resolves the top-level intent from explicit interface commands. Generation
is triggered only by an explicit command (/image, /video) so plain text
analysis messages never accidentally route to a generation backend.
"""

from __future__ import annotations

from enum import StrEnum

from assistant.core.models.intent import RequestIntent


class GenerationCommand(StrEnum):
    """Interface-level commands that select a generation intent."""

    IMAGE = "/image"
    VIDEO = "/video"


class IntentDetector:
    """Maps an explicit command/slug to a :class:`RequestIntent`.

    ``None`` ``command`` signposts the normal analysis path and always maps
    to :class:`RequestIntent.ANALYZE`.
    """

    @staticmethod
    def detect(command: str | None) -> RequestIntent:
        if not command:
            return RequestIntent.ANALYZE

        clean = command.strip().lstrip("/").lower()
        # Match the leading command slug so a trailing prompt or arguments
        # (e.g. "/image a red dragon") still resolve to the generation intent.
        if clean == "image" or clean.startswith("image "):
            return RequestIntent.GENERATE_IMAGE
        if clean == "video" or clean.startswith("video "):
            return RequestIntent.GENERATE_VIDEO
        return RequestIntent.ANALYZE

    @staticmethod
    def is_generation(intent: RequestIntent) -> bool:
        """True when the intent targets a media-generation backend."""
        return intent in (RequestIntent.GENERATE_IMAGE, RequestIntent.GENERATE_VIDEO)
