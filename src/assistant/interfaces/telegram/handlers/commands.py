"""Telegram command handlers."""

from aiogram import Bot, Router
from aiogram.enums import ChatAction
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, Message

from assistant.adapters.storage import preferences_repo
from assistant.config import TaskCategory, settings
from assistant.core.services.batch import BatchSummarizer, extract_urls
from assistant.core.services.context_store import context_store
from assistant.core.services.exporter import ExportFormat, document_exporter
from assistant.core.services.telemetry import telemetry_service
from assistant.interfaces.telegram.handlers.media import _execute_batch_and_reply
from assistant.interfaces.telegram.keyboards import (
    get_export_keyboard,
    get_settings_keyboard,
    get_status_keyboard,
)

router = Router(name="commands")

WELCOME_MESSAGE = """👋 **Привет! Я Assistant.**

Я умею принимать **абсолютно всё**:
• 🎙️ **Голосовые и аудио** ➔ Дословная расшифровка (STT) + Саммари
• 📹 **Видео и видеосообщения («кружочки»)** ➔ Извлечение звука + STT + Саммари
• 📄 **Документы (PDF, DOCX, TXT)** ➔ Анализ и выжимка главного
• 🖼️ **Фото, скриншоты, стикеры, GIF** ➔ Распознавание текста (OCR) и смысла
• 🔗 **Ссылки и статьи** ➔ Скачивание текста и структурированное саммари
• 🌐 **Несколько ссылок сразу (Batch)** ➔ Параллельный анализ и сводный синтез
• 💬 **Текстовые сообщения и заметки** ➔ TL;DR и ключевые тезисы
• 📍 **Геолокации** ➔ Описание контекста
• 🔍 **Inline-режим в любом чате** ➔ Набери `@Assistant <ссылка или слово>`
• 🎨 **Генерация изображений** ➔ `/image <описание>`
• 🎬 **Генерация видео** ➔ `/video <описание>`

Просто перешли или отправь мне любой контент!

⚙️ **Команды**:
/batch — мульти-источниковый параллельный анализ и синтез ссылок
/image — генерация изображения (Venice.AI, без цензуры)
/video — генерация видео (Venice.AI, без цензуры)
/settings — персональные настройки языка, глубины и формата
/export — экспорт последнего саммари в файл (Markdown, HTML, TXT)
/status — оперативная диагностика, аптайм и статистика кэша
/models — текущая матрица моделей (Primary / Fallback)
/help — подробная справка
"""

HELP_MESSAGE = """📖 **Справка по Assistant**

1. **Обычный режим**:
   Просто отправь боту файл, голосовое, видео, ссылку или текст. Бот автоматически определит категорию контента, извлечет суть и предоставит результат.

2. **Мульти-источниковый синтез (/batch)**:
   Отправь сразу несколько ссылок в одном сообщении (или используй команду `/batch <url1> <url2>...`). Бот параллельно извлечет контент из всех источников, составит обзор каждого из них и сформирует кросс-источниковый аналитический синтез.

3. **Inline-поиск и шаринг (@Assistant)**:
   В любом личном или групповом чате начни вводить `@Assistant` — бот покажет последние саммари. Введи ссылку `@Assistant https://...` для мгновенной отправки готового саммари или слово для поиска по твоей базе знаний.

4. **Генерация изображений и видео (/image, /video)**:
   `Assistant` умеет генерировать картинки и видео через Venice.AI — без цензуры. Для этого отправь `/image <описание>` или `/video <описание>`. Видео принимает опции длительности (`-d 10s`) и разрешения (`-r 1080p`). Генерация видео выполняется асинхронно и занимает от ~30 секунд до пары минут.

5. **Pro-режим (Глубокий анализ)**:
   Если тебе нужен максимально глубокий и подробный экспертный разбор документа или статьи, добавь подпись `/pro` к сообщению или документу.

6. **Отказоустойчивость**:
   Бот использует связку **Primary ➔ Fallback**. Если основная модель занята или перегружена, бот автоматически переключится на резервную модель, чтобы вы гарантированно получили ответ.
"""


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    """Send welcome message."""
    await message.answer(WELCOME_MESSAGE, parse_mode="Markdown")


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    """Send help message."""
    await message.answer(HELP_MESSAGE, parse_mode="Markdown")


@router.message(Command("models"))
async def cmd_models(message: Message) -> None:
    """Display configured models across all categories."""
    lines = ["🤖 **Матрица моделей Assistant**:\n"]
    for cat in TaskCategory:
        primary, fallback = settings.get_models_for_category(cat)
        lines.append(f"• **{cat.value}**:\n  ├ Primary: `{primary}`\n  └ Fallback: `{fallback}`")

    await message.answer("\n".join(lines), parse_mode="Markdown")


@router.message(Command("settings"))
async def cmd_settings(message: Message) -> None:
    """Display interactive settings card with preference toggles."""
    user_id = message.from_user.id if message.from_user else message.chat.id
    username = message.from_user.username if message.from_user else None
    prefs = await preferences_repo.get(user_id)
    card_text = prefs.format_settings_card(username=username)
    markup = get_settings_keyboard(prefs)
    await message.answer(card_text, parse_mode="Markdown", reply_markup=markup)


@router.message(Command("status", "diag"))
async def cmd_status(message: Message) -> None:
    """Display real-time operational telemetry, uptime, memory, and cache metrics."""
    snapshot = await telemetry_service.collect()
    report = snapshot.format_telegram_report()
    markup = get_status_keyboard()
    await message.answer(report, parse_mode="Markdown", reply_markup=markup)


@router.message(Command("export"))
async def cmd_export(message: Message) -> None:
    """Export the most recent summary for the user to a file (Markdown, HTML, Text)."""
    user_id = message.from_user.id if message.from_user else message.chat.id
    context = await context_store.get_latest_for_user(user_id)
    if not context:
        await message.answer(
            "⚠️ У вас пока нет активных сохраненных саммари для экспорта.\n"
            "Отправьте боту текст, ссылку, аудио или документ для анализа.",
            parse_mode="Markdown",
        )
        return

    # Check if a specific format was requested (e.g. /export md, /export html, /export txt)
    args = (message.text or "").strip().split()
    if len(args) > 1:
        requested_fmt = args[1].lower().lstrip(".-")
        if requested_fmt in ("md", "markdown"):
            target_fmt = ExportFormat.MARKDOWN
        elif requested_fmt in ("html", "pdf"):
            target_fmt = ExportFormat.HTML
        elif requested_fmt in ("txt", "text"):
            target_fmt = ExportFormat.TEXT
        else:
            await message.answer(
                f"Неизвестный формат `{requested_fmt}`. Доступны: `md`, `html`, `txt`.",
                parse_mode="Markdown",
            )
            return

        file_bytes, filename, _ = document_exporter.export(context, target_fmt)
        doc = BufferedInputFile(file_bytes, filename=filename)
        await message.answer_document(
            document=doc,
            caption=(
                f"📥 **Экспорт документа** (`{target_fmt.value.upper()}`)\n\n"
                f"• ID: `{context.cid}`\n"
                f"• Модель: `{context.model_used or 'OpenRouter'}`\n"
                f"• Байт: `{len(file_bytes):,}`"
            ),
            parse_mode="Markdown",
        )
        return

    # No argument provided -> show format selection keyboard
    markup = get_export_keyboard(context.cid)
    await message.answer(
        f"📥 **Экспорт материала** (`{context.cid}`)\n\n"
        "Выберите желаемый формат для загрузки документа:",
        parse_mode="Markdown",
        reply_markup=markup,
    )


@router.message(Command("batch"))
async def cmd_batch(
    message: Message,
    bot: Bot,
    batch_summarizer: BatchSummarizer,
) -> None:
    """Analyze multiple URLs concurrently and provide cross-source executive synthesis."""
    text = (message.text or "").replace("/batch", "", 1).strip()
    urls = extract_urls(text)
    if not urls:
        await message.answer(
            "ℹ️ **Команда /batch**: мульти-источниковый параллельный анализ и синтез ссылок.\n\n"
            "**Пример использования**:\n"
            "`/batch https://example.com/art1 https://example.com/art2`\n\n"
            "Вы также можете задать инструкцию или вопрос:\n"
            "`/batch Сравни подходы в статьях: https://... https://...`",
            parse_mode="Markdown",
        )
        return

    is_pro = "/pro" in text.lower() or "--pro" in text.lower()
    force_refresh = (
        "/refresh" in text.lower() or "--refresh" in text.lower() or "/force" in text.lower()
    )

    # User instruction is whatever text remains after removing /batch, /pro, /refresh and URLs
    instruction_text = text
    for word in ("/pro", "--pro", "/refresh", "--refresh", "/force"):
        instruction_text = instruction_text.replace(word, "")
    for u in urls:
        instruction_text = instruction_text.replace(u, "")
    user_instruction: str | None = instruction_text.strip() or None

    await bot.send_chat_action(message.chat.id, ChatAction.TYPING)
    status_msg = await message.reply(
        f"⏳ *Параллельно анализирую {len(urls)} источников и формирую синтез...*",
        parse_mode="Markdown",
    )
    await _execute_batch_and_reply(
        message=message,
        urls=urls,
        user_instruction=user_instruction,
        batch_summarizer=batch_summarizer,
        status_msg=status_msg,
        is_pro=is_pro,
        force_refresh=force_refresh,
    )
