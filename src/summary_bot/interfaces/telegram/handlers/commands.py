"""Telegram command handlers."""

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, Message

from summary_bot.adapters.storage import preferences_repo
from summary_bot.config import TaskCategory, settings
from summary_bot.core.services.context_store import context_store
from summary_bot.core.services.exporter import ExportFormat, document_exporter
from summary_bot.core.services.telemetry import telemetry_service
from summary_bot.interfaces.telegram.keyboards import (
    get_export_keyboard,
    get_settings_keyboard,
    get_status_keyboard,
)

router = Router(name="commands")

WELCOME_MESSAGE = """👋 **Привет! Я SummaryBot.**

Я умею принимать **абсолютно всё**:
• 🎙️ **Голосовые и аудио** ➔ Дословная расшифровка (STT) + Саммари
• 📹 **Видео и видеосообщения («кружочки»)** ➔ Извлечение звука + STT + Саммари
• 📄 **Документы (PDF, DOCX, TXT)** ➔ Анализ и выжимка главного
• 🖼️ **Фото, скриншоты, стикеры, GIF** ➔ Распознавание текста (OCR) и смысла
• 🔗 **Ссылки и статьи** ➔ Скачивание текста и структурированное саммари
• 💬 **Текстовые сообщения и заметки** ➔ TL;DR и ключевые тезисы
• 📍 **Геолокации** ➔ Описание контекста

Просто перешли или отправь мне любой контент!

⚙️ **Команды**:
/settings — персональные настройки языка, глубины и формата
/export — экспорт последнего саммари в файл (Markdown, HTML, TXT)
/status — оперативная диагностика, аптайм и статистика кэша
/models — текущая матрица моделей (Primary / Fallback)
/help — подробная справка
"""

HELP_MESSAGE = """📖 **Справка по SummaryBot**

1. **Обычный режим**:
   Просто отправь боту файл, голосовое, видео, ссылку или текст. Бот автоматически определит категорию контента, извлечет суть и предоставит результат.

2. **Pro-режим (Глубокий анализ)**:
   Если тебе нужен максимально глубокий и подробный экспертный разбор документа или статьи, добавь подпись `/pro` к сообщению или документу.

3. **Отказоустойчивость**:
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
    lines = ["🤖 **Матрица моделей SummaryBot**:\n"]
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
