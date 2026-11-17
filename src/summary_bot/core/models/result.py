"""Domain model for processing results."""

from pydantic import BaseModel, Field

from summary_bot.config import TaskCategory


class ProcessingResult(BaseModel):
    """Unified result output from the processing pipeline."""

    category: TaskCategory
    summary: str
    transcription: str | None = None
    key_takeaways: list[str] = Field(default_factory=list)
    model_used: str
    used_fallback: bool = False
    from_cache: bool = False
    duration_seconds: float = 0.0
    tokens_prompt: int | None = None
    tokens_completion: int | None = None
    original_media_type: str | None = None

    def format_telegram_message(self) -> str:
        """Format the result as a rich, structured Telegram message."""
        parts: list[str] = []

        # If audio/video was transcribed, show transcription first
        if self.transcription:
            clean_transcript = self.transcription.strip()
            # If transcription is very long, format it nicely
            parts.append(f"🎙️ **Расшифровка (STT)**:\n{clean_transcript}\n")

        # Summary header & body
        parts.append(f"📝 **Саммари**:\n{self.summary.strip()}")

        # Key takeaways if present and not already inside summary
        if self.key_takeaways:
            takeaways_formatted = "\n".join(f"• {t.strip()}" for t in self.key_takeaways)
            parts.append(f"\n💡 **Главные мысли**:\n{takeaways_formatted}")

        # Metadata footer
        footer = f"\n—\n🤖 *Модель: {self.model_used}*"
        if self.from_cache:
            footer += " `⚡ [кэш]`"
        elif self.used_fallback:
            footer += " `[fallback]`"
        footer += f" • {self.duration_seconds:.2f}s"
        parts.append(footer)

        return "\n".join(parts)
