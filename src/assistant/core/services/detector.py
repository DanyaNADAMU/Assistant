"""Category detection service for incoming payloads."""

from assistant.config import TaskCategory
from assistant.core.models.payload import InputPayload, PayloadKind


class CategoryDetector:
    """Heuristic detector mapping InputPayload to appropriate TaskCategory."""

    @staticmethod
    def detect(payload: InputPayload) -> TaskCategory:
        """Determine task category based on payload modality, size, and flags."""
        # 1. Pro flag takes precedence for deep analysis
        if payload.is_pro:
            return TaskCategory.PRO

        # 2. Audio/Video payloads (speech, music, кружочки, voice)
        if payload.has_audio_stream:
            return TaskCategory.AUDIO_VIDEO

        # 3. Visual payloads (photos, stickers, gifs)
        if payload.has_visual_stream:
            return TaskCategory.VISION

        # 4. Geolocation coordinates
        if payload.kind == PayloadKind.LOCATION:
            return TaskCategory.MICRO

        # 5. Documents and web links
        if payload.kind in (PayloadKind.DOCUMENT, PayloadKind.URL):
            return TaskCategory.TEXT_DOCS

        # 6. Plain text messages
        if payload.kind == PayloadKind.TEXT:
            text = (payload.text or "").strip()
            # Micro messages (short greetings, reactions, simple queries < 150 chars)
            if len(text) < 150 and not text.startswith("http"):
                return TaskCategory.MICRO
            return TaskCategory.TEXT_DOCS

        # Default fallback
        return TaskCategory.TEXT_DOCS
