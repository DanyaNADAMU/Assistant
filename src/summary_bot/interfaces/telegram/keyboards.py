"""Inline keyboards for interactive message actions."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def get_summary_keyboard(
    cid: str,
    active_view: str = "orig",
    has_transcription: bool = False,
) -> InlineKeyboardMarkup:
    """Build dynamic inline keyboard for summary refinement actions."""
    builder = InlineKeyboardBuilder()

    if active_view != "orig":
        builder.row(
            InlineKeyboardButton(text="↩️ Исходное саммари", callback_data=f"act:{cid}:orig")
        )

    action_buttons: list[InlineKeyboardButton] = []
    if active_view != "tldr":
        action_buttons.append(
            InlineKeyboardButton(text="📌 Кратко", callback_data=f"act:{cid}:tldr")
        )
    if active_view != "actions":
        action_buttons.append(
            InlineKeyboardButton(text="📋 Задачи", callback_data=f"act:{cid}:actions")
        )
    if active_view != "deep":
        action_buttons.append(
            InlineKeyboardButton(text="🔍 Подробнее", callback_data=f"act:{cid}:deep")
        )
    if active_view != "trans":
        action_buttons.append(
            InlineKeyboardButton(text="🌐 EN ↔ RU", callback_data=f"act:{cid}:trans")
        )

    # Place action buttons in rows of 2
    for i in range(0, len(action_buttons), 2):
        builder.row(*action_buttons[i : i + 2])

    if has_transcription and active_view != "stt":
        builder.row(
            InlineKeyboardButton(text="🎙️ Полный транскрипт", callback_data=f"act:{cid}:stt")
        )

    return builder.as_markup()
