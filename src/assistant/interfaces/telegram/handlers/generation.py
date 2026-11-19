"""Telegram media-generation handlers (/image and /video)."""

import contextlib

from aiogram import Bot, Router
from aiogram.enums import ChatAction
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, Message

from assistant.adapters.venice import VeniceClient
from assistant.config import settings
from assistant.core.models.generated import GeneratedMediaError
from assistant.core.services.media_generator import MediaGenerator

router = Router(name="generation")

MAX_PROMPT_LEN = 2000


def _extract_prompt(text: str | None, command: str) -> str | None:
    """Return the prompt after the command, or None if empty."""
    if not text:
        return None
    clean = text.replace(command, "", 1).strip()
    return clean or None


async def _delete_status_suppressed(status: Message) -> None:
    """Best-effort delete of the transient status message (never raises)."""
    with contextlib.suppress(Exception):
        await status.delete()


@router.message(Command("image"))
async def cmd_image(message: Message, bot: Bot) -> None:
    """Generate an image with Venice.AI from a text prompt."""
    prompt = _extract_prompt(message.text, "/image")
    if not prompt:
        await message.answer(
            "🖼️ **Генерация изображения**\n\n"
            "Отправь команду вместе с описанием:\n`/image <описание картинки>`\n\n"
            "Пример:\n`/image маленький кот в скафандре на луне, фотореализм`",
            parse_mode="Markdown",
        )
        return
    if len(prompt) > MAX_PROMPT_LEN:
        await message.answer(
            f"⚠️ Слишком длинный промпт (макс. {MAX_PROMPT_LEN} символов).",
            parse_mode="Markdown",
        )
        return

    await bot.send_chat_action(message.chat.id, ChatAction.UPLOAD_PHOTO)
    status = await message.reply(
        f"🎨 *Генерирую изображение...* `{prompt[:80]}`", parse_mode="Markdown"
    )

    try:
        generator = MediaGenerator(venice=VeniceClient(settings=settings), settings=settings)
        result = await generator.generate_image(prompt)
        media = result.media
        filename = f"generated-{media.model_used.split('/')[-1]}.{media.default_extension}"
        photo = BufferedInputFile(media.content_bytes, filename=filename)
        await message.answer_photo(
            photo=photo,
            caption=(
                f"🖼️ **Сгенерировано**: `{media.model_used}` "
                f"({len(media.content_bytes):,} байт, {media.elapsed_seconds:.1f}s)"
            ),
            parse_mode="Markdown",
        )
    except GeneratedMediaError as exc:
        await message.answer(
            f"⚠️ *Ошибка генерации изображения*:\n`{exc.message[:400]}`", parse_mode="Markdown"
        )
    except Exception as exc:  # noqa: BLE001 - surface unexpected failures to the user
        await message.answer(f"⚠️ *Неожиданная ошибка*: `{exc!s}`", parse_mode="Markdown")
    finally:
        await _delete_status_suppressed(status)


@router.message(Command("video"))
async def cmd_video(message: Message, bot: Bot) -> None:
    """Generate a video with Venice.AI from a text prompt."""

    def _arg(name: str) -> str | None:
        parts = (message.text or "").split()
        mode = None
        for i, tok in enumerate(parts):
            if tok == name and i + 1 < len(parts):
                mode = parts[i + 1]
        return mode

    prompt = _extract_prompt(message.text, "/video")
    duration = _arg("-d") or _arg("--duration") or settings.gen_video_duration
    resolution = _arg("-r") or _arg("--resolution") or settings.gen_video_resolution
    if not prompt:
        await message.answer(
            "🎬 **Генерация видео**\n\n"
            "Отправь команду с описанием:\n`/video <описание>`\n\n"
            "Опции:\n`-d 10s` — длительность (5s/10s)\n`-r 1080p` — разрешение (480p/720p/1080p)\n\n"
            "Пример:\n`/video дрон летит над венецианскими каналами -d 10s -r 1080p`",
            parse_mode="Markdown",
        )
        return
    if len(prompt) > MAX_PROMPT_LEN:
        await message.answer(
            f"⚠️ Слишком длинный промпт (макс. {MAX_PROMPT_LEN} символов).",
            parse_mode="Markdown",
        )
        return

    await bot.send_chat_action(message.chat.id, ChatAction.UPLOAD_VIDEO)
    status = await message.reply(
        f"🎬 *Генерирую видео* (`{duration}`/`{resolution}`)... `{prompt[:80]}`",
        parse_mode="Markdown",
    )

    try:
        generator = MediaGenerator(venice=VeniceClient(settings=settings), settings=settings)
        result = await generator.generate_video(
            prompt,
            duration=duration,
            resolution=resolution,
        )
        media = result.media
        filename = f"video-{media.model_used.split('/')[-1]}.{media.default_extension}"
        video_file = BufferedInputFile(media.content_bytes, filename=filename)
        await message.answer_video(
            video=video_file,
            caption=(
                f"🎬 **Сгенерировано**: `{media.model_used}` "
                f"({duration}/{resolution}, {len(media.content_bytes):,} байт, "
                f"{media.elapsed_seconds:.1f}s)"
            ),
            parse_mode="Markdown",
        )
    except GeneratedMediaError as exc:
        await message.answer(
            f"⚠️ *Ошибка генерации видео*:\n`{exc.message[:400]}`", parse_mode="Markdown"
        )
    except Exception as exc:  # noqa: BLE001
        await message.answer(f"⚠️ *Неожиданная ошибка*: `{exc!s}`", parse_mode="Markdown")
    finally:
        await _delete_status_suppressed(status)
