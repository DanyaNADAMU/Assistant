"""Document export service generating structured Markdown, HTML, and Text reports."""

import html
import re
from datetime import UTC, datetime
from enum import StrEnum

from summary_bot.core.services.context_store import SummaryContext


class ExportFormat(StrEnum):
    """Supported document export formats."""

    MARKDOWN = "md"
    HTML = "html"
    TEXT = "txt"

    @property
    def extension(self) -> str:
        """File extension."""
        return f".{self.value}"

    @property
    def mime_type(self) -> str:
        """MIME type for file delivery."""
        match self:
            case ExportFormat.MARKDOWN:
                return "text/markdown; charset=utf-8"
            case ExportFormat.HTML:
                return "text/html; charset=utf-8"
            case ExportFormat.TEXT:
                return "text/plain; charset=utf-8"

    @property
    def label(self) -> str:
        """Human-readable display label."""
        match self:
            case ExportFormat.MARKDOWN:
                return "Markdown (.md)"
            case ExportFormat.HTML:
                return "HTML / Print to PDF (.html)"
            case ExportFormat.TEXT:
                return "Plain Text (.txt)"


class DocumentExporter:
    """Renders SummaryContext into downloadable documents with metadata."""

    def export(
        self,
        context: SummaryContext,
        format_type: ExportFormat | str,
        title: str = "Сводка материала",
    ) -> tuple[bytes, str, str]:
        """Export context to specified format.

        Returns:
            Tuple of (file_bytes, filename, mime_type).
        """
        fmt = ExportFormat(format_type) if isinstance(format_type, str) else format_type
        timestamp = datetime.fromtimestamp(context.created_at, tz=UTC).strftime("%Y%m%d_%H%M%S")
        filename = f"summary_{context.cid}_{timestamp}{fmt.extension}"

        match fmt:
            case ExportFormat.MARKDOWN:
                content = self.render_markdown(context, title=title)
            case ExportFormat.HTML:
                content = self.render_html(context, title=title)
            case ExportFormat.TEXT:
                content = self.render_text(context, title=title)

        return content.encode("utf-8"), filename, fmt.mime_type

    def render_markdown(self, context: SummaryContext, title: str = "Сводка материала") -> str:
        """Render context as rich Markdown document with metadata frontmatter."""
        dt_str = datetime.fromtimestamp(context.created_at, tz=UTC).strftime(
            "%Y-%m-%d %H:%M:%S UTC"
        )
        category_name = (
            context.category.value if hasattr(context.category, "value") else str(context.category)
        )

        lines: list[str] = [
            f"# 📄 {title}",
            "",
            f"> **ID документа**: `{context.cid}`  ",
            f"> **Категория**: {category_name}  ",
            f"> **Модель генерации**: `{context.model_used or 'OpenRouter'}`  ",
            f"> **Дата генерации**: {dt_str}  ",
            "",
            "---",
            "",
            "## 📌 Основное содержание (Summary)",
            "",
            context.summary.strip(),
            "",
        ]

        if context.key_takeaways:
            lines.extend(
                [
                    "## 📋 Ключевые тезисы и выводы (Key Takeaways)",
                    "",
                ]
            )
            for item in context.key_takeaways:
                clean_item = item.strip()
                if not clean_item.startswith(("-", "*", "•")):
                    clean_item = f"- {clean_item}"
                lines.append(clean_item)
            lines.append("")

        # Include additional views if user generated them
        if context.views:
            lines.extend(
                [
                    "## 🔍 Дополнительные разделы и выжимки",
                    "",
                ]
            )
            for view_name, view_content in context.views.items():
                label = self._format_view_title(view_name)
                # Strip out the bot signature from cached telegram views
                clean_view = self._strip_telegram_decorations(view_content)
                lines.extend(
                    [
                        f"### {label}",
                        "",
                        clean_view,
                        "",
                    ]
                )

        if context.transcription:
            lines.extend(
                [
                    "## 🎙️ Стенограмма речи (Transcription)",
                    "",
                    context.transcription.strip(),
                    "",
                ]
            )

        lines.extend(
            [
                "---",
                "*Сгенерировано автоматически мультимодальным ботом [SummaryBot](https://git.nada.mu/NADAMU/SummaryBot)*",
            ]
        )

        return "\n".join(lines)

    def render_html(self, context: SummaryContext, title: str = "Сводка материала") -> str:
        """Render context as standalone, modern, responsive HTML with print stylesheet."""
        dt_str = datetime.fromtimestamp(context.created_at, tz=UTC).strftime(
            "%Y-%m-%d %H:%M:%S UTC"
        )
        category_name = (
            context.category.value if hasattr(context.category, "value") else str(context.category)
        )

        # Convert simple markdown paragraphs and lists to HTML
        summary_html = self._markdown_to_simple_html(context.summary)

        takeaways_html = ""
        if context.key_takeaways:
            items_html = "".join(
                f"<li>{html.escape(item.lstrip('-*• '))}</li>" for item in context.key_takeaways
            )
            takeaways_html = f"""
            <section class="section">
                <h2>📋 Ключевые тезисы</h2>
                <ul class="takeaways-list">
                    {items_html}
                </ul>
            </section>
            """

        views_html = ""
        if context.views:
            views_blocks = []
            for view_name, view_content in context.views.items():
                clean_view = self._strip_telegram_decorations(view_content)
                views_blocks.append(f"""
                <div class="sub-section">
                    <h3>{html.escape(self._format_view_title(view_name))}</h3>
                    {self._markdown_to_simple_html(clean_view)}
                </div>
                """)
            views_html = f"""
            <section class="section">
                <h2>🔍 Дополнительные аналитические выжимки</h2>
                {"".join(views_blocks)}
            </section>
            """

        transcription_html = ""
        if context.transcription:
            transcription_html = f"""
            <section class="section">
                <h2>🎙️ Стенограмма речи</h2>
                <div class="transcription-box">
                    <pre>{html.escape(context.transcription.strip())}</pre>
                </div>
            </section>
            """

        return f"""<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{html.escape(title)} — {html.escape(context.cid)}</title>
    <style>
        :root {{
            --bg-color: #f8fafc;
            --card-bg: #ffffff;
            --text-primary: #1e293b;
            --text-secondary: #64748b;
            --accent: #2563eb;
            --border-color: #e2e8f0;
            --code-bg: #f1f5f9;
        }}
        @media (prefers-color-scheme: dark) {{
            :root {{
                --bg-color: #0f172a;
                --card-bg: #1e293b;
                --text-primary: #f8fafc;
                --text-secondary: #94a3b8;
                --accent: #3b82f6;
                --border-color: #334155;
                --code-bg: #0f172a;
            }}
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            line-height: 1.65;
            color: var(--text-primary);
            background-color: var(--bg-color);
            margin: 0;
            padding: 2rem 1rem;
        }}
        .container {{
            max-width: 840px;
            margin: 0 auto;
            background: var(--card-bg);
            padding: 2.5rem;
            border-radius: 12px;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
            border: 1px solid var(--border-color);
        }}
        h1 {{
            margin-top: 0;
            font-size: 2rem;
            border-bottom: 2px solid var(--border-color);
            padding-bottom: 0.75rem;
            color: var(--text-primary);
        }}
        h2 {{
            font-size: 1.35rem;
            color: var(--accent);
            margin-top: 2rem;
            margin-bottom: 0.75rem;
        }}
        h3 {{
            font-size: 1.1rem;
            color: var(--text-primary);
            margin-top: 1.25rem;
            margin-bottom: 0.5rem;
        }}
        .meta-box {{
            background: var(--code-bg);
            border-left: 4px solid var(--accent);
            padding: 0.75rem 1.25rem;
            margin-bottom: 2rem;
            border-radius: 0 6px 6px 0;
            font-size: 0.9rem;
            color: var(--text-secondary);
        }}
        .meta-item {{
            margin: 0.2rem 0;
        }}
        .meta-label {{
            font-weight: 600;
            color: var(--text-primary);
        }}
        .section {{
            margin-bottom: 2rem;
        }}
        .takeaways-list {{
            padding-left: 1.5rem;
        }}
        .takeaways-list li {{
            margin-bottom: 0.5rem;
        }}
        .transcription-box pre {{
            background: var(--code-bg);
            padding: 1rem;
            border-radius: 8px;
            white-space: pre-wrap;
            word-break: break-word;
            font-family: inherit;
            font-size: 0.95rem;
            max-height: 500px;
            overflow-y: auto;
            border: 1px solid var(--border-color);
        }}
        .footer {{
            margin-top: 3rem;
            padding-top: 1rem;
            border-top: 1px solid var(--border-color);
            text-align: center;
            font-size: 0.85rem;
            color: var(--text-secondary);
        }}
        .footer a {{
            color: var(--accent);
            text-decoration: none;
        }}
        .print-btn {{
            float: right;
            background: var(--accent);
            color: white;
            border: none;
            padding: 0.5rem 1rem;
            border-radius: 6px;
            cursor: pointer;
            font-size: 0.9rem;
            font-weight: 500;
        }}
        .print-btn:hover {{
            opacity: 0.9;
        }}
        @media print {{
            body {{
                background: white;
                color: black;
                padding: 0;
            }}
            .container {{
                box-shadow: none;
                border: none;
                padding: 0;
                max-width: 100%;
            }}
            .print-btn, .footer {{
                display: none;
            }}
            .meta-box {{
                border-left-color: #666;
                background: #eee;
            }}
            h2 {{
                color: black;
            }}
            a {{
                text-decoration: underline;
                color: black;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <button class="print-btn" onclick="window.print()">🖨️ Печать / PDF</button>
        <h1>📄 {html.escape(title)}</h1>
        <div class="meta-box">
            <div class="meta-item"><span class="meta-label">ID:</span> <code>{html.escape(context.cid)}</code></div>
            <div class="meta-item"><span class="meta-label">Категория:</span> {html.escape(category_name)}</div>
            <div class="meta-item"><span class="meta-label">Модель:</span> {html.escape(context.model_used or "OpenRouter")}</div>
            <div class="meta-item"><span class="meta-label">Дата:</span> {html.escape(dt_str)}</div>
        </div>

        <section class="section">
            <h2>📌 Основное содержание</h2>
            {summary_html}
        </section>

        {takeaways_html}
        {views_html}
        {transcription_html}

        <div class="footer">
            Сгенерировано автоматически мультимодальным сервисом <a href="https://git.nada.mu/NADAMU/SummaryBot">SummaryBot</a>
        </div>
    </div>
</body>
</html>"""

    def render_text(self, context: SummaryContext, title: str = "Сводка материала") -> str:
        """Render context as clean plain-text report."""
        dt_str = datetime.fromtimestamp(context.created_at, tz=UTC).strftime(
            "%Y-%m-%d %H:%M:%S UTC"
        )
        category_name = (
            context.category.value if hasattr(context.category, "value") else str(context.category)
        )

        sep = "=" * 60
        sub_sep = "-" * 60

        lines: list[str] = [
            sep,
            f" {title.upper()}",
            sep,
            f"ID:        {context.cid}",
            f"Категория: {category_name}",
            f"Модель:    {context.model_used or 'OpenRouter'}",
            f"Дата:      {dt_str}",
            sep,
            "",
            "[ ОСНОВНОЕ СОДЕРЖАНИЕ / SUMMARY ]",
            sub_sep,
            context.summary.strip(),
            "",
        ]

        if context.key_takeaways:
            lines.extend(
                [
                    "[ КЛЮЧЕВЫЕ ТЕЗИСЫ И ВЫВОДЫ ]",
                    sub_sep,
                ]
            )
            for item in context.key_takeaways:
                clean_item = item.strip().lstrip("-*• ")
                lines.append(f" * {clean_item}")
            lines.append("")

        if context.views:
            lines.extend(
                [
                    "[ ДОПОЛНИТЕЛЬНЫЕ РАЗДЕЛЫ ]",
                    sub_sep,
                ]
            )
            for view_name, view_content in context.views.items():
                label = self._format_view_title(view_name)
                clean_view = self._strip_telegram_decorations(view_content)
                lines.extend(
                    [
                        f">> {label}",
                        clean_view.strip(),
                        "",
                    ]
                )

        if context.transcription:
            lines.extend(
                [
                    "[ СТЕНОГРАММА РЕЧИ / TRANSCRIPTION ]",
                    sub_sep,
                    context.transcription.strip(),
                    "",
                ]
            )

        lines.extend(
            [
                sub_sep,
                "SummaryBot (c) 2026 https://git.nada.mu/NADAMU/SummaryBot",
                sep,
            ]
        )

        return "\n".join(lines)

    @staticmethod
    def _format_view_title(action: str) -> str:
        """Format view action name to readable title."""
        match action:
            case "tldr":
                return "📌 Краткая суть (TL;DR)"
            case "actions":
                return "📋 Задачи и действия (Action Items)"
            case "deep":
                return "🔍 Детальный аналитический разбор"
            case "trans":
                return "🌐 Перевод (Translation)"
            case _:
                return f"Выжимка ({action})"

    @staticmethod
    def _strip_telegram_decorations(text: str) -> str:
        """Strip telegram markdown decorations and footer signatures from view content."""
        # Remove trailing footer like "\n\n—\n🤖 *model*"
        cleaned = re.sub(r"\n+—\n+🤖\s*\*[^*]+\*", "", text)
        return cleaned.strip()

    @staticmethod
    def _markdown_to_simple_html(md: str) -> str:
        """Convert basic Markdown paragraphs, bold/italic, and bullet lists to HTML."""
        lines = md.strip().splitlines()
        html_parts: list[str] = []
        in_list = False

        for line in lines:
            line_str = line.strip()
            if not line_str:
                if in_list:
                    html_parts.append("</ul>")
                    in_list = False
                continue

            if line_str.startswith(("-", "*", "•")):
                if not in_list:
                    html_parts.append("<ul>")
                    in_list = True
                item_content = line_str.lstrip("-*• ")
                html_parts.append(f"<li>{DocumentExporter._format_inline_html(item_content)}</li>")
            else:
                if in_list:
                    html_parts.append("</ul>")
                    in_list = False
                html_parts.append(f"<p>{DocumentExporter._format_inline_html(line_str)}</p>")

        if in_list:
            html_parts.append("</ul>")

        return "\n".join(html_parts)

    @staticmethod
    def _format_inline_html(text: str) -> str:
        """Escape text and replace basic inline markdown (**bold**, *italic*, `code`)."""
        escaped = html.escape(text)
        # Bold **text**
        escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
        # Italic *text*
        escaped = re.sub(r"\*(.+?)\*", r"<em>\1</em>", escaped)
        # Code `text`
        escaped = re.sub(r"`(.+?)`", r"<code>\1</code>", escaped)
        return escaped


# Global exporter service instance
document_exporter = DocumentExporter()
