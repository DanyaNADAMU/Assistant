"""Unit tests for DocumentExporter and export suite capabilities."""

import pytest

from summary_bot.config import TaskCategory
from summary_bot.core.services.context_store import SummaryContext, SummaryContextStore
from summary_bot.core.services.exporter import (
    DocumentExporter,
    ExportFormat,
    document_exporter,
)
from summary_bot.interfaces.telegram.keyboards import (
    get_export_keyboard,
    get_summary_keyboard,
)


@pytest.fixture
def sample_context() -> SummaryContext:
    """Fixture returning a sample SummaryContext with metadata and views."""
    ctx = SummaryContext.create(
        original_text="Original formatted summary text",
        source_content="Raw speech transcript or document content here.",
        summary="This is the main comprehensive summary of the project architecture.",
        transcription="Full audio transcript spoken by the speaker in the podcast.",
        key_takeaways=[
            "Trunk-based development ensures linear immutable git timeline.",
            "Rootless Podman Quadlets isolate production containers safely.",
            "Always sign commits with SSH key.",
        ],
        category=TaskCategory.AUDIO_VIDEO,
        model_used="google/gemini-2.5-flash",
        user_id=123456,
    )
    ctx.views["tldr"] = (
        "📌 **Краткая суть (TL;DR)**:\n\nDeploying rootless containers with Quadlets.\n\n—\n🤖 *google/gemini-2.5-flash*"
    )
    ctx.views["actions"] = (
        "📋 **Задачи и действия (Action Items)**:\n\n1. Review quadlets.\n2. Merge PR.\n\n—\n🤖 *google/gemini-2.5-flash*"
    )
    return ctx


def test_export_format_enum() -> None:
    """Verify ExportFormat enum properties."""
    assert ExportFormat.MARKDOWN.extension == ".md"
    assert "markdown" in ExportFormat.MARKDOWN.mime_type
    assert ExportFormat.HTML.extension == ".html"
    assert "html" in ExportFormat.HTML.mime_type
    assert ExportFormat.TEXT.extension == ".txt"
    assert "plain" in ExportFormat.TEXT.mime_type


def test_render_markdown(sample_context: SummaryContext) -> None:
    """Test Markdown document rendering."""
    md = document_exporter.render_markdown(sample_context, title="Архитектурный отчет")

    assert "# 📄 Архитектурный отчет" in md
    assert f"> **ID документа**: `{sample_context.cid}`" in md
    assert "google/gemini-2.5-flash" in md
    assert "## 📌 Основное содержание (Summary)" in md
    assert sample_context.summary in md
    assert "## 📋 Ключевые тезисы и выводы (Key Takeaways)" in md
    assert "Trunk-based development ensures linear immutable git timeline." in md
    assert "## 🔍 Дополнительные разделы и выжимки" in md
    assert "📌 Краткая суть (TL;DR)" in md
    assert "Deploying rootless containers with Quadlets." in md
    assert "## 🎙️ Стенограмма речи (Transcription)" in md
    assert sample_context.transcription in md
    # Telegram bot footer should be stripped
    assert "🤖 *google/gemini-2.5-flash*" not in md


def test_render_html(sample_context: SummaryContext) -> None:
    """Test HTML5 document rendering with print styles."""
    html_content = document_exporter.render_html(sample_context, title="Веб-отчет")

    assert "<!DOCTYPE html>" in html_content
    assert '<html lang="ru">' in html_content
    assert "<title>Веб-отчет —" in html_content
    assert "@media print" in html_content
    assert "🖨️ Печать / PDF" in html_content
    assert sample_context.summary in html_content
    assert '<ul class="takeaways-list">' in html_content
    assert "<li>Rootless Podman Quadlets isolate production containers safely.</li>" in html_content
    assert "🎙️ Стенограмма речи" in html_content
    assert "<pre>" in html_content
    assert "SummaryBot" in html_content


def test_render_text(sample_context: SummaryContext) -> None:
    """Test clean plain text report rendering."""
    txt = document_exporter.render_text(sample_context, title="Текстовый отчет")

    assert "ТЕКСТОВЫЙ ОТЧЕТ" in txt
    assert sample_context.cid in txt
    assert "[ ОСНОВНОЕ СОДЕРЖАНИЕ / SUMMARY ]" in txt
    assert sample_context.summary in txt
    assert "[ КЛЮЧЕВЫЕ ТЕЗИСЫ И ВЫВОДЫ ]" in txt
    assert " * Always sign commits with SSH key." in txt
    assert "[ СТЕНОГРАММА РЕЧИ / TRANSCRIPTION ]" in txt


def test_export_bytes(sample_context: SummaryContext) -> None:
    """Test export byte output and filenames across formats."""
    exporter = DocumentExporter()

    for fmt in (ExportFormat.MARKDOWN, ExportFormat.HTML, ExportFormat.TEXT):
        file_bytes, filename, mime = exporter.export(sample_context, fmt)
        assert isinstance(file_bytes, bytes)
        assert len(file_bytes) > 100
        assert filename.startswith(f"summary_{sample_context.cid}_")
        assert filename.endswith(fmt.extension)
        assert mime == fmt.mime_type


@pytest.mark.asyncio
async def test_context_store_user_tracking() -> None:
    """Test retrieval of latest context for specific user IDs."""
    store = SummaryContextStore(max_size=10, ttl_seconds=3600.0)

    ctx1 = SummaryContext.create("t1", "s1", "sum1", user_id=100)
    ctx2 = SummaryContext.create("t2", "s2", "sum2", user_id=200)
    ctx3 = SummaryContext.create("t3", "s3", "sum3", user_id=100)

    await store.put(ctx1)
    await store.put(ctx2)
    await store.put(ctx3)

    latest_100 = await store.get_latest_for_user(100)
    assert latest_100 is not None
    assert latest_100.cid == ctx3.cid

    latest_200 = await store.get_latest_for_user(200)
    assert latest_200 is not None
    assert latest_200.cid == ctx2.cid

    latest_unknown = await store.get_latest_for_user(999)
    assert latest_unknown is None


def test_export_keyboards() -> None:
    """Verify export inline keyboard construction."""
    markup = get_summary_keyboard("test1234", active_view="orig", has_transcription=True)
    # Check that export button is present
    buttons = [btn for row in markup.inline_keyboard for btn in row]
    assert any(btn.callback_data == "act:test1234:export" for btn in buttons)

    export_markup = get_export_keyboard("test1234")
    exp_buttons = [btn for row in export_markup.inline_keyboard for btn in row]
    data_list = [btn.callback_data for btn in exp_buttons]
    assert "exp:test1234:md" in data_list
    assert "exp:test1234:html" in data_list
    assert "exp:test1234:txt" in data_list
    assert "act:test1234:orig" in data_list
