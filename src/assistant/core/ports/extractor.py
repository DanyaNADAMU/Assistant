"""Port definition for Media Extractor."""

from typing import Protocol, runtime_checkable

from assistant.core.models.payload import InputPayload


@runtime_checkable
class MediaExtractorPort(Protocol):
    """Protocol for extracting normalized text or audio from diverse media types."""

    async def can_handle(self, payload: InputPayload) -> bool:
        """Check if this extractor handles the given payload."""
        ...

    async def extract(self, payload: InputPayload) -> InputPayload:
        """Extract and enrich payload with clean text or extracted audio stream."""
        ...
