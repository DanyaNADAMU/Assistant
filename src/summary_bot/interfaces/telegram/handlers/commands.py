"""Telegram command handlers."""

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from summary_bot.config import TaskCategory, settings

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
