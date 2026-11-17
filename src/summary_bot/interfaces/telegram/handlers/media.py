"""Telegram media and text message handlers."""

import logging
from pathlib import Path

from aiogram import Bot, F, Router
from aiogram.enums import ChatAction
from aiogram.types import Message

from summary_bot.config import settings
from summary_bot.core.models.payload import InputPayload, PayloadKind
from summary_bot.core.services.context_store import SummaryContext, context_store
from summary_bot.core.services.runner import ResilientModelRunner
from summary_bot.interfaces.telegram.downloader import FileTooLargeError, download_telegram_file
from summary_bot.interfaces.telegram.keyboards import get_summary_keyboard

logger = logging.getLogger(__name__)
router = Router(name="media")

MAX_TELEGRAM_MESSAGE_LENGTH = 4000


def _is_pro(caption: str | None, text: str | None) -> bool:
    """Check if /pro flag is specified in message text or caption."""
    combined = f"{caption or ''} {text or ''}".lower()
    return "/pro" in combined or "--pro" in combined


async def _execute_and_reply(
    message: Message,
    payload: InputPayload,
    runner: ResilientModelRunner,
    status_msg: Message,
) -> None:
    """Execute runner and send formatted results to user, handling message length limits."""
    try:
        result = await runner.run(payload)
        formatted_text = result.format_telegram_message()

        # Build context for interactive buttons
        source_content = result.transcription or result.summary
        if result.key_takeaways:
            source_content += "\n\n" + "\n".join(result.key_takeaways)

        ctx = SummaryContext.create(
            original_text=formatted_text,
            source_content=source_content,
            summary=result.summary,
            transcription=result.transcription,
            key_takeaways=result.key_takeaways,
            category=result.category,
            model_used=result.model_used,
        )
        await context_store.put(ctx)
        reply_markup = get_summary_keyboard(
            cid=ctx.cid,
            active_view="orig",
            has_transcription=bool(result.transcription),
        )

        # Split message if it exceeds Telegram's 4096 character limit
        if len(formatted_text) <= MAX_TELEGRAM_MESSAGE_LENGTH:
            await status_msg.edit_text(
                formatted_text, parse_mode="Markdown", reply_markup=reply_markup
            )
        else:
            await status_msg.delete()
            chunks = [
                formatted_text[i : i + MAX_TELEGRAM_MESSAGE_LENGTH]
                for i in range(0, len(formatted_text), MAX_TELEGRAM_MESSAGE_LENGTH)
            ]
            for idx, chunk in enumerate(chunks):
                markup = reply_markup if idx == len(chunks) - 1 else None
                await message.reply(chunk, parse_mode="Markdown", reply_markup=markup)
    except Exception as exc:
        logger.exception("Failed to process message %s: %s", message.message_id, exc)
        await status_msg.edit_text(
            f"❌ **Произошла ошибка при обработке**:\n`{exc}`\n\nПопробуйте повторить запрос позже.",
            parse_mode="Markdown",
        )


@router.message(F.voice)
async def handle_voice(message: Message, bot: Bot, runner: ResilientModelRunner) -> None:
    """Handle voice messages."""
    assert message.voice is not None
    await bot.send_chat_action(message.chat.id, ChatAction.RECORD_VOICE)
    status_msg = await message.reply("⏳ *Слушаю и расшифровываю голосовое...*", parse_mode="Markdown")

    try:
        async with download_telegram_file(
            bot=bot,
            file_id=message.voice.file_id,
            max_size_bytes=settings.max_download_size_bytes,
            custom_suffix=".ogg",
        ) as file_path:
            payload = InputPayload(
                kind=PayloadKind.VOICE,
                file_path=file_path,
                mime_type=message.voice.mime_type or "audio/ogg",
                is_pro=_is_pro(message.caption, None),
            )
            await _execute_and_reply(message, payload, runner, status_msg)
    except FileTooLargeError as err:
        await status_msg.edit_text(f"⚠️ {err}")


@router.message(F.video_note)
async def handle_video_note(message: Message, bot: Bot, runner: ResilientModelRunner) -> None:
    """Handle circular video notes ("кружочки")."""
    assert message.video_note is not None
    await bot.send_chat_action(message.chat.id, ChatAction.RECORD_VIDEO_NOTE)
    status_msg = await message.reply("⏳ *Анализирую видеосообщение...*", parse_mode="Markdown")

    try:
        async with download_telegram_file(
            bot=bot,
            file_id=message.video_note.file_id,
            max_size_bytes=settings.max_download_size_bytes,
            custom_suffix=".mp4",
        ) as file_path:
            payload = InputPayload(
                kind=PayloadKind.VIDEO_NOTE,
                file_path=file_path,
                mime_type="video/mp4",
                is_pro=_is_pro(message.caption, None),
            )
            await _execute_and_reply(message, payload, runner, status_msg)
    except FileTooLargeError as err:
        await status_msg.edit_text(f"⚠️ {err}")


@router.message(F.audio)
async def handle_audio(message: Message, bot: Bot, runner: ResilientModelRunner) -> None:
    """Handle audio files and music."""
    assert message.audio is not None
    await bot.send_chat_action(message.chat.id, ChatAction.RECORD_VOICE)
    status_msg = await message.reply("⏳ *Обрабатываю аудиофайл...*", parse_mode="Markdown")

    try:
        async with download_telegram_file(
            bot=bot,
            file_id=message.audio.file_id,
            max_size_bytes=settings.max_download_size_bytes,
            custom_suffix=Path(message.audio.file_name or "audio.mp3").suffix or ".mp3",
        ) as file_path:
            payload = InputPayload(
                kind=PayloadKind.AUDIO,
                file_path=file_path,
                filename=message.audio.file_name,
                mime_type=message.audio.mime_type or "audio/mpeg",
                is_pro=_is_pro(message.caption, None),
            )
            await _execute_and_reply(message, payload, runner, status_msg)
    except FileTooLargeError as err:
        await status_msg.edit_text(f"⚠️ {err}")


@router.message(F.video)
async def handle_video(message: Message, bot: Bot, runner: ResilientModelRunner) -> None:
    """Handle video files."""
    assert message.video is not None
    await bot.send_chat_action(message.chat.id, ChatAction.RECORD_VIDEO)
    status_msg = await message.reply("⏳ *Извлекаю звук и анализирую видео...*", parse_mode="Markdown")

    try:
        async with download_telegram_file(
            bot=bot,
            file_id=message.video.file_id,
            max_size_bytes=settings.max_download_size_bytes,
            custom_suffix=Path(message.video.file_name or "video.mp4").suffix or ".mp4",
        ) as file_path:
            payload = InputPayload(
                kind=PayloadKind.VIDEO,
                file_path=file_path,
                filename=message.video.file_name,
                mime_type=message.video.mime_type or "video/mp4",
                is_pro=_is_pro(message.caption, None),
            )
            await _execute_and_reply(message, payload, runner, status_msg)
    except FileTooLargeError as err:
        await status_msg.edit_text(f"⚠️ {err}")


@router.message(F.document)
async def handle_document(message: Message, bot: Bot, runner: ResilientModelRunner) -> None:
    """Handle documents (PDF, DOCX, TXT, images sent as uncompressed files, etc.)."""
    assert message.document is not None
    await bot.send_chat_action(message.chat.id, ChatAction.TYPING)

    filename = message.document.file_name or "doc.pdf"
    ext = Path(filename).suffix.lower()
    mime = message.document.mime_type or ""

    is_image = mime.startswith("image/") or ext in (
        ".jpg",
        ".jpeg",
        ".png",
        ".webp",
        ".bmp",
        ".gif",
        ".tiff",
    )
    status_text = (
        "⏳ *Анализирую изображение...*"
        if is_image
        else "⏳ *Читаю и структурирую документ...*"
    )
    status_msg = await message.reply(status_text, parse_mode="Markdown")

    try:
        async with download_telegram_file(
            bot=bot,
            file_id=message.document.file_id,
            max_size_bytes=settings.max_download_size_bytes,
            custom_suffix=ext or ".pdf",
        ) as file_path:
            kind = PayloadKind.IMAGE if is_image else PayloadKind.DOCUMENT
            payload = InputPayload(
                kind=kind,
                file_path=file_path,
                filename=filename,
                mime_type=mime or ("image/jpeg" if is_image else None),
                text=message.caption,
                is_pro=_is_pro(message.caption, None),
            )
            await _execute_and_reply(message, payload, runner, status_msg)
    except FileTooLargeError as err:
        await status_msg.edit_text(f"⚠️ {err}")


@router.message(F.photo)
async def handle_photo(message: Message, bot: Bot, runner: ResilientModelRunner) -> None:
    """Handle photo messages."""
    assert message.photo is not None
    await bot.send_chat_action(message.chat.id, ChatAction.TYPING)
    status_msg = await message.reply("⏳ *Распознаю изображение...*", parse_mode="Markdown")

    largest_photo = message.photo[-1]
    try:
        async with download_telegram_file(
            bot=bot,
            file_id=largest_photo.file_id,
            max_size_bytes=settings.max_download_size_bytes,
            custom_suffix=".jpg",
        ) as file_path:
            payload = InputPayload(
                kind=PayloadKind.IMAGE,
                file_path=file_path,
                mime_type="image/jpeg",
                text=message.caption,
                is_pro=_is_pro(message.caption, None),
            )
            await _execute_and_reply(message, payload, runner, status_msg)
    except FileTooLargeError as err:
        await status_msg.edit_text(f"⚠️ {err}")


@router.message(F.sticker)
async def handle_sticker(message: Message, bot: Bot, runner: ResilientModelRunner) -> None:
    """Handle stickers."""
    assert message.sticker is not None
    await bot.send_chat_action(message.chat.id, ChatAction.TYPING)
    status_msg = await message.reply("⏳ *Анализирую стикер...*", parse_mode="Markdown")

    # Static webp sticker or fallback to emoji description
    emoji_hint = message.sticker.emoji or ""
    try:
        async with download_telegram_file(
            bot=bot,
            file_id=message.sticker.file_id,
            max_size_bytes=settings.max_download_size_bytes,
            custom_suffix=".webp",
        ) as file_path:
            payload = InputPayload(
                kind=PayloadKind.STICKER,
                file_path=file_path,
                mime_type="image/webp",
                text=f"Стикер с эмодзи-подсказкой: {emoji_hint}" if emoji_hint else "Стикер",
            )
            await _execute_and_reply(message, payload, runner, status_msg)
    except Exception:
        # Fallback to emoji description if sticker binary fails
        payload = InputPayload(kind=PayloadKind.TEXT, text=f"Стикер {emoji_hint}")
        await _execute_and_reply(message, payload, runner, status_msg)


@router.message(F.animation)
async def handle_animation(message: Message, bot: Bot, runner: ResilientModelRunner) -> None:
    """Handle GIF animations."""
    assert message.animation is not None
    await bot.send_chat_action(message.chat.id, ChatAction.TYPING)
    status_msg = await message.reply("⏳ *Анализирую GIF...*", parse_mode="Markdown")

    try:
        async with download_telegram_file(
            bot=bot,
            file_id=message.animation.file_id,
            max_size_bytes=settings.max_download_size_bytes,
            custom_suffix=".mp4",
        ) as file_path:
            payload = InputPayload(
                kind=PayloadKind.GIF,
                file_path=file_path,
                mime_type=message.animation.mime_type or "video/mp4",
                text=message.caption,
            )
            await _execute_and_reply(message, payload, runner, status_msg)
    except FileTooLargeError as err:
        await status_msg.edit_text(f"⚠️ {err}")


@router.message(F.location)
async def handle_location(message: Message, bot: Bot, runner: ResilientModelRunner) -> None:
    """Handle geolocation pins."""
    assert message.location is not None
    await bot.send_chat_action(message.chat.id, ChatAction.TYPING)
    status_msg = await message.reply("⏳ *Определяю контекст локации...*", parse_mode="Markdown")

    payload = InputPayload(
        kind=PayloadKind.LOCATION,
        latitude=message.location.latitude,
        longitude=message.location.longitude,
    )
    await _execute_and_reply(message, payload, runner, status_msg)


@router.message(F.text)
async def handle_text(message: Message, bot: Bot, runner: ResilientModelRunner) -> None:
    """Handle plain text messages and links."""
    assert message.text is not None
    text = message.text.strip()
    is_pro = _is_pro(None, text)

    # Clean /pro trigger from input text
    cleaned_text = text.replace("/pro", "").replace("--pro", "").strip()

    await bot.send_chat_action(message.chat.id, ChatAction.TYPING)
    status_msg = await message.reply("⏳ *Анализирую текст...*", parse_mode="Markdown")

    if cleaned_text.startswith(("http://", "https://")):
        payload = InputPayload(kind=PayloadKind.URL, url=cleaned_text, is_pro=is_pro)
    else:
        payload = InputPayload(kind=PayloadKind.TEXT, text=cleaned_text, is_pro=is_pro)

    await _execute_and_reply(message, payload, runner, status_msg)
