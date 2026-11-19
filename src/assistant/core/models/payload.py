"""Domain models for payload and processing results."""

import hashlib
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
    force_refresh: bool = False
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

    def compute_content_hash(self) -> str:
        """Compute a deterministic SHA-256 fingerprint for the payload content."""
        hasher = hashlib.sha256()

        # 1. Binary payload in memory
        if self.content_bytes:
            hasher.update(self.content_bytes)
            return hasher.hexdigest()

        # 2. File payload on disk
        if self.file_path and self.file_path.is_file():
            with self.file_path.open("rb") as f:
                while chunk := f.read(65536):
                    hasher.update(chunk)
            return hasher.hexdigest()

        # 3. Web URL
        if self.url:
            clean_url = self.url.strip()
            hasher.update(f"url:{clean_url}".encode())
            return hasher.hexdigest()

        # 4. Text content
        if self.text:
            clean_text = self.text.strip()
            hasher.update(f"text:{clean_text}".encode())
            return hasher.hexdigest()

        # 5. Geolocation
        if self.latitude is not None and self.longitude is not None:
            hasher.update(f"geo:{self.latitude:.6f}:{self.longitude:.6f}".encode())
            return hasher.hexdigest()

        # Fallback to kind
        hasher.update(f"kind:{self.kind.value}".encode())
        return hasher.hexdigest()
