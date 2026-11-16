"""Domain models for payload and processing results."""

from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class PayloadKind(StrEnum):
    """Specific media or content kind of the input payload."""

    TEXT = "text"
    URL = "url"
    VOICE = "voice"
    AUDIO = "audio"
    VIDEO = "video"
    VIDEO_NOTE = "video_note"  # Telegram circular video note ("кружочек")
    DOCUMENT = "document"
    IMAGE = "image"
    STICKER = "sticker"
    GIF = "gif"
    LOCATION = "location"


class InputPayload(BaseModel):
    """Normalized universal input payload representation."""

    kind: PayloadKind
    text: str | None = None
    url: str | None = None
    file_path: Path | None = None
    content_bytes: bytes | None = None
    mime_type: str | None = None
    filename: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    is_pro: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def has_audio_stream(self) -> bool:
        """Check if payload potentially contains audio to transcribe."""
        return self.kind in (
            PayloadKind.VOICE,
            PayloadKind.AUDIO,
            PayloadKind.VIDEO,
            PayloadKind.VIDEO_NOTE,
        )

    @property
    def has_visual_stream(self) -> bool:
        """Check if payload contains static or dynamic visual elements."""
        return self.kind in (
            PayloadKind.IMAGE,
            PayloadKind.STICKER,
            PayloadKind.GIF,
        )
