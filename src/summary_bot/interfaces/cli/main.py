"""CLI interface for SummaryBot using Typer and Rich."""

import asyncio
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from summary_bot.adapters.extractors.audio import AudioExtractor
from summary_bot.adapters.extractors.document import DocumentExtractor
from summary_bot.adapters.extractors.web import WebExtractor
from summary_bot.adapters.openrouter.client import OpenRouterClient
from summary_bot.config import TaskCategory, settings
from summary_bot.core.models.payload import InputPayload, PayloadKind
from summary_bot.core.services.runner import ResilientModelRunner

app = typer.Typer(
    name="summary-bot",
    help="Universal Multimodal Summarization, STT & Synthesis Suite",
    no_args_is_help=True,
)
console = Console()


def _resolve_payload(target: str, is_pro: bool) -> InputPayload:
    """Analyze input string and map to appropriate InputPayload."""
    path = Path(target)
    if path.exists() and path.is_file():
        ext = path.suffix.lower()
        if ext in (".mp3", ".wav", ".ogg", ".oga", ".m4a", ".aac"):
            return InputPayload(kind=PayloadKind.AUDIO, file_path=path, filename=path.name, is_pro=is_pro)
        if ext in (".mp4", ".mov", ".mkv", ".webm", ".avi"):
            return InputPayload(kind=PayloadKind.VIDEO, file_path=path, filename=path.name, is_pro=is_pro)
        if ext in (".jpg", ".jpeg", ".png", ".webp", ".bmp"):
            return InputPayload(kind=PayloadKind.IMAGE, file_path=path, filename=path.name, is_pro=is_pro)
        if ext in (".pdf", ".docx", ".txt", ".md"):
            return InputPayload(kind=PayloadKind.DOCUMENT, file_path=path, filename=path.name, is_pro=is_pro)
        return InputPayload(kind=PayloadKind.DOCUMENT, file_path=path, filename=path.name, is_pro=is_pro)

    if target.startswith(("http://", "https://")):
        return InputPayload(kind=PayloadKind.URL, url=target, is_pro=is_pro)

    return InputPayload(kind=PayloadKind.TEXT, text=target, is_pro=is_pro)


@app.command()
def process(
    target: Annotated[str, typer.Argument(help="File path, URL, or raw text to process")],
    pro: Annotated[bool, typer.Option("--pro", "-p", help="Enable deep analytical Pro mode")] = False,
    output: Annotated[Path | None, typer.Option("--output", "-o", help="Save output to file")] = None,
    as_json: Annotated[bool, typer.Option("--json", help="Output results in JSON format")] = False,
) -> None:
    """Ingest any media file, URL, or text, returning transcription and structured summary."""

    async def _async_process() -> None:
        payload = _resolve_payload(target, is_pro=pro)
        gateway = OpenRouterClient(settings=settings)
        extractors = [AudioExtractor(), DocumentExtractor(), WebExtractor()]
        runner = ResilientModelRunner(gateway=gateway, settings=settings, extractors=extractors)

        with console.status("[bold cyan]Обработка мультимодального конвейера...", spinner="dots"):
            result = await runner.run(payload)

        if as_json:
            console.print_json(result.model_dump_json(indent=2))
            return

        if result.transcription:
            console.print(
                Panel(
                    result.transcription,
                    title="🎙️ [bold yellow]Расшифровка речи (STT)[/bold yellow]",
                    border_style="yellow",
                )
            )

        console.print(
            Panel(
                Markdown(result.summary),
                title="📝 [bold green]Саммари контента[/bold green]",
                border_style="green",
            )
        )

        badge = f"[bold cyan]Модель:[/bold cyan] {result.model_used}"
        if result.used_fallback:
            badge += " [bold magenta][FALLBACK][/bold magenta]"
        badge += f" | [dim]{result.duration_seconds:.2f}s[/dim]"

        console.print(badge)

        if output:
            output.write_text(result.format_telegram_message(), encoding="utf-8")
            console.print(f"[dim]Результат сохранен в {output}[/dim]")

    asyncio.run(_async_process())


@app.command()
def models() -> None:
    """Display configured models matrix across all task categories."""
    table = Table(title="🤖 Матрица моделей SummaryBot (OpenRouter)", border_style="cyan")
    table.add_column("Категория", style="bold white")
    table.add_column("Primary модель (Основная)", style="green")
    table.add_column("Fallback модель (Резервная)", style="yellow")

    for cat in TaskCategory:
        primary, fallback = settings.get_models_for_category(cat)
        table.add_row(cat.value, primary, fallback)

    console.print(table)


if __name__ == "__main__":
    app()
