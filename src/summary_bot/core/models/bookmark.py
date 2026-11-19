"""Domain models for user bookmarks and knowledge archive."""

from datetime import UTC, datetime

from pydantic import BaseModel, Field


class BookmarkItem(BaseModel):
    """A bookmarked summary entry in the personal knowledge archive."""

    id: int | None = None
    user_id: int
    context_id: str
    title: str
    source_url: str | None = None
    summary_text: str
    takeaways: list[str] = Field(default_factory=list)
    category: str = "general"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def format_preview(self, index: int = 1) -> str:
        """Format concise preview for paginated list display."""
        date_str = self.created_at.strftime("%d.%m.%Y")
        source_part = f" — [{self.source_url}]({self.source_url})" if self.source_url else ""
        short_summary = self.summary_text.strip().replace("\n", " ")
        if len(short_summary) > 160:
            short_summary = short_summary[:157] + "..."
        return f"**{index}. {self.title}**{source_part}\n📅 _{date_str}_ | {short_summary}\n"

    def format_full(self) -> str:
        """Format detailed view of the bookmark."""
        date_str = self.created_at.strftime("%d.%m.%Y %H:%M UTC")
        source_line = f"\n🔗 **Источник:** {self.source_url}" if self.source_url else ""
        takeaways_section = ""
        if self.takeaways:
            items_str = "\n".join(f"• {item}" for item in self.takeaways)
            takeaways_section = f"\n\n💡 **Главные мысли:**\n{items_str}"

        return (
            f"⭐ **{self.title}**{source_line}\n"
            f"📅 _Сохранено: {date_str}_\n\n"
            f"📝 **Краткое содержание:**\n{self.summary_text}"
            f"{takeaways_section}"
        )
