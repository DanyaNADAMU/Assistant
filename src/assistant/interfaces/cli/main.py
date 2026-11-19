"""CLI interface for Assistant using Typer and Rich."""

import asyncio
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from assistant.adapters.extractors.audio import AudioExtractor
from assistant.adapters.extractors.document import DocumentExtractor
from assistant.adapters.extractors.vision import VisionExtractor
from assistant.adapters.extractors.web import WebExtractor
from assistant.adapters.openrouter.client import OpenRouterClient
from assistant.adapters.storage import response_cache
from assistant.adapters.venice import VeniceClient
from assistant.config import TaskCategory, settings
from assistant.core.models.payload import InputPayload, PayloadKind
from assistant.core.services.batch import BatchSummarizer
from assistant.core.services.context_store import SummaryContext
from assistant.core.services.exporter import document_exporter
from assistant.core.services.media_generator import MediaGenerator
from assistant.core.services.runner import ResilientModelRunner
from assistant.core.services.telemetry import telemetry_service
from assistant.interfaces.telegram.bot import start_telegram_bot

app = typer.Typer(
    name="assistant",
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
            return InputPayload(
                kind=PayloadKind.AUDIO, file_path=path, filename=path.name, is_pro=is_pro
            )
        if ext in (".mp4", ".mov", ".mkv", ".webm", ".avi"):
            return InputPayload(
                kind=PayloadKind.VIDEO, file_path=path, filename=path.name, is_pro=is_pro
            )
        if ext in (".jpg", ".jpeg", ".png", ".webp", ".bmp"):
            return InputPayload(
                kind=PayloadKind.IMAGE, file_path=path, filename=path.name, is_pro=is_pro
            )
        if ext in (".pdf", ".docx", ".txt", ".md"):
            return InputPayload(
                kind=PayloadKind.DOCUMENT, file_path=path, filename=path.name, is_pro=is_pro
            )
        return InputPayload(
            kind=PayloadKind.DOCUMENT, file_path=path, filename=path.name, is_pro=is_pro
        )

    if target.startswith(("http://", "https://")):
        return InputPayload(kind=PayloadKind.URL, url=target, is_pro=is_pro)

    return InputPayload(kind=PayloadKind.TEXT, text=target, is_pro=is_pro)


@app.command()
def process(
    target: Annotated[str, typer.Argument(help="File path, URL, or raw text to process")],
    pro: Annotated[
        bool, typer.Option("--pro", "-p", help="Enable deep analytical Pro mode")
    ] = False,
    refresh: Annotated[
        bool, typer.Option("--refresh", "-r", help="Bypass cache and force fresh summarization")
    ] = False,
    output: Annotated[
        Path | None, typer.Option("--output", "-o", help="Save output to file")
    ] = None,
    as_json: Annotated[bool, typer.Option("--json", help="Output results in JSON format")] = False,
) -> None:
    """Ingest any media file, URL, or text, returning transcription and structured summary."""

    async def _async_process() -> None:
        payload = _resolve_payload(target, is_pro=pro)
        payload.force_refresh = refresh
        gateway = OpenRouterClient(settings=settings)
        extractors = [AudioExtractor(), DocumentExtractor(), VisionExtractor(), WebExtractor()]
        runner = ResilientModelRunner(
            gateway=gateway,
            settings=settings,
            extractors=extractors,
            cache=response_cache,
        )

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
        if result.from_cache:
            badge += " [bold green]⚡ [КЭШ][/bold green]"
        elif result.used_fallback:
            badge += " [bold magenta][FALLBACK][/bold magenta]"
        badge += f" | [dim]{result.duration_seconds:.2f}s[/dim]"

        console.print(badge)

        if output:
            ext = output.suffix.lower().lstrip(".")
            if ext in ("md", "html", "txt"):
                ctx = SummaryContext.create(
                    original_text=result.format_telegram_message(),
                    source_content=result.transcription or result.summary,
                    summary=result.summary,
                    transcription=result.transcription,
                    key_takeaways=result.key_takeaways,
                    category=result.category,
                    model_used=result.model_used,
                )
                file_bytes, _, _ = document_exporter.export(
                    ctx,
                    ext,
                    title=Path(target).name if Path(target).exists() else "Сводка материала",
                )
                output.write_bytes(file_bytes)
            else:
                output.write_text(result.format_telegram_message(), encoding="utf-8")
            console.print(f"[dim]Результат сохранен в {output}[/dim]")

    asyncio.run(_async_process())


@app.command("export")
def export_file(
    target: Annotated[
        str, typer.Argument(help="File path, URL, or raw text to process and export")
    ],
    format_type: Annotated[
        str, typer.Option("--format", "-f", help="Export format: md, html, txt")
    ] = "md",
    output: Annotated[
        Path | None, typer.Option("--output", "-o", help="Target output file path")
    ] = None,
    pro: Annotated[bool, typer.Option("--pro", "-p", help="Enable Pro analytical mode")] = False,
) -> None:
    """Process any media/link/text and export directly to a structured Markdown, HTML, or TXT document."""

    async def _async_export() -> None:
        payload = _resolve_payload(target, is_pro=pro)
        gateway = OpenRouterClient(settings=settings)
        extractors = [AudioExtractor(), DocumentExtractor(), VisionExtractor(), WebExtractor()]
        runner = ResilientModelRunner(
            gateway=gateway,
            settings=settings,
            extractors=extractors,
            cache=response_cache,
        )

        with console.status(
            f"[bold cyan]Обработка и экспорт в {format_type.upper()}...", spinner="dots"
        ):
            result = await runner.run(payload)

        source_content = result.transcription or result.summary
        if result.key_takeaways:
            source_content += "\n\n" + "\n".join(result.key_takeaways)

        ctx = SummaryContext.create(
            original_text=result.format_telegram_message(),
            source_content=source_content,
            summary=result.summary,
            transcription=result.transcription,
            key_takeaways=result.key_takeaways,
            category=result.category,
            model_used=result.model_used,
        )

        target_title = Path(target).name if Path(target).exists() else "Сводка материала"
        file_bytes, default_name, _ = document_exporter.export(ctx, format_type, title=target_title)
        out_path = output or Path(default_name)
        out_path.write_bytes(file_bytes)
        console.print(
            f"[bold green]✓[/bold green] Документ успешно экспортирован: [bold cyan]{out_path}[/bold cyan] ({len(file_bytes):,} байт)"
        )

    asyncio.run(_async_export())


@app.command("cache-stats")
def cache_stats() -> None:
    """Display persistent cache deduplication metrics."""

    async def _async_stats() -> None:
        stats = await response_cache.get_stats()
        table = Table(title="⚡ Статистика кэширования Assistant", border_style="green")
        table.add_column("Метрика", style="bold white")
        table.add_column("Значение", style="cyan")
        table.add_row("Сохраненных саммари", str(stats.summary_count))
        table.add_row("Попаданий в кэш (Саммари)", str(stats.summary_hits))
        table.add_row("Сохраненных уточнений", str(stats.refinement_count))
        table.add_row("Попаданий в кэш (Уточнения)", str(stats.refinement_hits))
        table.add_row("Всего записей", str(stats.total_entries))
        table.add_row("Всего попаданий (Hits)", str(stats.total_hits))
        table.add_row("Эффективность (Hit Rate)", f"{stats.hit_rate:.1f}%")
        console.print(table)

    asyncio.run(_async_stats())


@app.command()
def models() -> None:
    """Display configured models matrix across all task categories."""
    table = Table(title="🤖 Матрица моделей Assistant (OpenRouter)", border_style="cyan")
    table.add_column("Категория", style="bold white")
    table.add_column("Primary модель (Основная)", style="green")
    table.add_column("Fallback модель (Резервная)", style="yellow")

    for cat in TaskCategory:
        primary, fallback = settings.get_models_for_category(cat)
        table.add_row(cat.value, primary, fallback)

    console.print(table)


@app.command()
def image(
    prompt: Annotated[str, typer.Argument(help="Text description of the image to generate")],
    output: Annotated[
        Path | None, typer.Option("--output", "-o", help="Save the generated image to a file")
    ] = None,
    model: Annotated[
        str | None, typer.Option("--model", "-m", help="Override the Venice image model")
    ] = None,
) -> None:
    """Generate an image with Venice.AI (uncensored) from a text prompt."""

    async def _async_generate() -> None:
        venice = VeniceClient(settings=settings)
        generator = MediaGenerator(venice=venice, settings=settings)

        effective_model = model or settings.gen_image_model
        with console.status(
            f"[bold magenta]Генерация изображения ({effective_model})...", spinner="dots"
        ):
            media = await generator.generate_image(prompt, output_path=output)

        if output is None:
            ext = media.media.default_extension
            out = Path(f"generated-image.{ext}")
            media.media.to_file(out)
        else:
            out = output

        console.print(
            Panel(
                f"[bold]Готово![/bold] Изображение сгенерировано моделью [cyan]{media.media.model_used}[/cyan].",
                title="🖼️ Assistant — Генерация изображения",
                border_style="magenta",
            )
        )
        console.print(
            f"[dim]→ Сохранено: {out} ({len(media.media.content_bytes):,} байт, {media.media.elapsed_seconds:.1f}s)[/dim]"
        )

    asyncio.run(_async_generate())


@app.command()
def video(
    prompt: Annotated[str, typer.Argument(help="Text description of the video to generate")],
    from_image: Annotated[
        Path | None,
        typer.Option("--from-image", "-i", help="Optional source image for image-to-video"),
    ] = None,
    output: Annotated[
        Path | None, typer.Option("--output", "-o", help="Save the generated video to a file")
    ] = None,
    model: Annotated[
        str | None, typer.Option("--model", "-m", help="Override the Venice video model")
    ] = None,
) -> None:
    """Generate a video with Venice.AI (uncensored) from a text prompt (and optional image)."""

    async def _async_generate() -> None:
        venice = VeniceClient(settings=settings)
        generator = MediaGenerator(venice=venice, settings=settings)

        from_bytes: bytes | None = None
        from_mime: str | None = None
        if from_image is not None:
            if not from_image.exists():
                raise typer.BadParameter(f"Source image not found: {from_image}")
            from_bytes = from_image.read_bytes()
            from_mime = "image/webp" if from_image.suffix.lower() == ".webp" else "image/png"

        effective_model = model or (
            settings.gen_video_image_model
            if from_bytes is not None
            else settings.gen_video_text_model
        )
        with console.status(
            f"[bold magenta]Генерация видео ({effective_model})...", spinner="dots"
        ):
            media = await generator.generate_video(
                prompt,
                from_image_bytes=from_bytes,
                from_image_mime=from_mime,
                output_path=output,
            )

        if output is None:
            out = Path(f"generated-video.{media.media.default_extension}")
            media.media.to_file(out)
        else:
            out = output

        console.print(
            Panel(
                f"[bold]Готово![/bold] Видео сгенерировано моделью [cyan]{media.media.model_used}[/cyan].",
                title="🎬 Assistant — Генерация видео",
                border_style="magenta",
            )
        )
        console.print(
            f"[dim]→ Сохранено: {out} ({len(media.media.content_bytes):,} байт, {media.media.elapsed_seconds:.1f}s)[/dim]"
        )

    asyncio.run(_async_generate())


@app.command("tg-serve")
def tg_serve() -> None:
    """Launch the Telegram Bot long-polling daemon service."""
    console.print("[bold cyan]Запуск сервиса Telegram бота Assistant...[/bold cyan]")
    asyncio.run(start_telegram_bot())


@app.command("status")
def status_cmd() -> None:
    """Display real-time operational telemetry, memory, and database diagnostics."""

    async def _async_diag() -> None:
        snapshot = await telemetry_service.collect()
        table = Table(
            title=f"📊 Диагностика и статус Assistant ({snapshot.environment})",
            border_style="cyan",
        )
        table.add_column("Компонент", style="bold white")
        table.add_column("Метрика / Значение", style="green")

        table.add_row("Среда (Environment)", snapshot.environment)
        table.add_row("Аптайм (Uptime)", snapshot.uptime_formatted)
        table.add_row("Память (Resident RSS)", f"{snapshot.memory_rss_mb:.1f} МБ")
        table.add_row("Размер базы данных SQLite", f"{snapshot.db_size_kb:.1f} КБ")
        table.add_row("Размер журнала WAL", f"{snapshot.wal_size_kb:.1f} КБ")
        table.add_row("Зарегистрированных пользователей", str(snapshot.registered_users))
        table.add_row("Саммари в кэше", str(snapshot.cache_stats.summary_count))
        table.add_row("Попаданий в кэш (Саммари)", str(snapshot.cache_stats.summary_hits))
        table.add_row("Уточнений в кэше", str(snapshot.cache_stats.refinement_count))
        table.add_row("Эффективность кэша", f"{snapshot.cache_stats.hit_rate:.1f}%")

        console.print(table)

    asyncio.run(_async_diag())


@app.command("batch")
def batch_urls(
    urls: Annotated[
        list[str],
        typer.Argument(help="List of URLs to concurrently summarize and synthesize"),
    ],
    instruction: Annotated[
        str | None,
        typer.Option("--instruction", "-i", help="Custom analytical prompt or comparison query"),
    ] = None,
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Target output file (supports .md, .html, .txt)"),
    ] = None,
    pro: Annotated[bool, typer.Option("--pro", "-p", help="Enable Pro analytical mode")] = False,
    refresh: Annotated[
        bool, typer.Option("--refresh", "-r", help="Bypass cache and force re-generation")
    ] = False,
) -> None:
    """Process multiple URLs concurrently and produce a cross-source analytical synthesis."""

    async def _async_batch() -> None:
        gateway = OpenRouterClient(settings=settings)
        extractors = [AudioExtractor(), DocumentExtractor(), VisionExtractor(), WebExtractor()]
        runner = ResilientModelRunner(
            gateway=gateway,
            settings=settings,
            extractors=extractors,
            cache=response_cache,
        )
        batch_summarizer = BatchSummarizer(
            runner=runner,
            gateway=gateway,
            settings=settings,
        )

        with console.status(
            f"[bold cyan]Параллельный анализ {len(urls)} источников и синтез...", spinner="dots"
        ):
            batch_result = await batch_summarizer.summarize_batch(
                urls=urls,
                user_instruction=instruction,
                is_pro=pro,
                force_refresh=refresh,
            )

        formatted_msg = batch_result.format_telegram_message()
        console.print(
            Panel(
                Markdown(formatted_msg),
                title="🌐 Мульти-источниковый аналитический обзор",
                border_style="cyan",
            )
        )

        if output:
            ext = output.suffix.lower().lstrip(".")
            if ext in ("md", "html", "txt"):
                source_content_blocks = [
                    f"Мульти-источниковый аналитический обзор ({batch_result.successful_sources}/{batch_result.total_sources})",
                    f"Синтез:\n{batch_result.synthesis}",
                ]
                for item in batch_result.items:
                    source_content_blocks.append(f"Источник: {item.url}\n{item.summary}")
                    if item.key_takeaways:
                        source_content_blocks.append("Тезисы:\n" + "\n".join(item.key_takeaways))

                ctx = SummaryContext.create(
                    original_text=formatted_msg,
                    source_content="\n\n".join(source_content_blocks),
                    summary=batch_result.synthesis,
                    transcription=None,
                    key_takeaways=[],
                    category=TaskCategory.TEXT_DOCS,
                    model_used=batch_result.synthesis_model,
                )
                file_bytes, _, _ = document_exporter.export(
                    ctx,
                    ext,
                    title="Мульти-источниковый аналитический обзор",
                )
                output.write_bytes(file_bytes)
            else:
                output.write_text(formatted_msg, encoding="utf-8")
            console.print(f"[dim]Результат сохранен в {output}[/dim]")

    asyncio.run(_async_batch())


@app.command("healthcheck")
def healthcheck() -> None:
    """Validate runtime health for container and systemd watchdogs (exit 0 on healthy)."""
    healthy = telemetry_service.is_healthy()
    if healthy:
        console.print("[bold green]OK: Assistant service healthy[/bold green]")
        raise typer.Exit(code=0)

    console.print("[bold red]ERROR: Assistant service unhealthy[/bold red]")
    raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
