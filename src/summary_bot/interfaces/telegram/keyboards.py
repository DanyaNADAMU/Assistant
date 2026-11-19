"""Inline keyboards for interactive message actions."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from summary_bot.core.models.user_preferences import UserPreferences


def get_summary_keyboard(
    cid: str,
    active_view: str = "orig",
    has_transcription: bool = False,
    is_bookmarked: bool = False,
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

    # Bookmark toggle and export buttons on bottom row
    bm_text = "⭐ В закладках" if is_bookmarked else "☆ В закладки"
    builder.row(
        InlineKeyboardButton(text=bm_text, callback_data=f"bm:toggle:{cid}"),
        InlineKeyboardButton(text="📥 Экспорт", callback_data=f"act:{cid}:export"),
    )

    return builder.as_markup()


def get_export_keyboard(cid: str) -> InlineKeyboardMarkup:
    """Build inline keyboard for document format export selection."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📝 Markdown (.md)", callback_data=f"exp:{cid}:md"),
        InlineKeyboardButton(text="🌐 HTML / PDF (.html)", callback_data=f"exp:{cid}:html"),
    )
    builder.row(
        InlineKeyboardButton(text="📄 Текст (.txt)", callback_data=f"exp:{cid}:txt"),
        InlineKeyboardButton(text="↩️ Назад к саммари", callback_data=f"act:{cid}:orig"),
    )
    return builder.as_markup()


def get_settings_keyboard(preferences: UserPreferences) -> InlineKeyboardMarkup:
    """Build interactive inline keyboard for user preferences toggling."""
    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(
            text=f"🌐 Язык: {preferences.language.label}",
            callback_data="pref:lang",
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=f"📝 Глубина: {preferences.depth.label}",
            callback_data="pref:depth",
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=f"📐 Формат: {preferences.format.label}",
            callback_data="pref:format",
        )
    )
    action_status = "Вкл ✅" if preferences.include_action_items else "Выкл ❌"
    builder.row(
        InlineKeyboardButton(
            text=f"📋 Список задач: {action_status}",
            callback_data="pref:actions",
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="🔄 Сбросить по умолчанию",
            callback_data="pref:reset",
        )
    )

    return builder.as_markup()


def get_status_keyboard() -> InlineKeyboardMarkup:
    """Build inline keyboard for status and diagnostics card."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🔄 Обновить статус", callback_data="status:refresh"),
        InlineKeyboardButton(text="⚙️ Настройки", callback_data="status:settings"),
    )
    return builder.as_markup()


def get_bookmarks_page_keyboard(
    bookmark_ids: list[int],
    page: int,
    total_pages: int,
    query: str | None = None,
) -> InlineKeyboardMarkup:
    """Build paginated keyboard for bookmarks archive."""
    builder = InlineKeyboardBuilder()

    # Row of item selectors: 📖 #1, 📖 #2, etc.
    item_buttons = [
        InlineKeyboardButton(
            text=f"📖 #{idx + 1}",
            callback_data=f"bm:open:{b_id}:{page}",
        )
        for idx, b_id in enumerate(bookmark_ids)
    ]
    if item_buttons:
        builder.row(*item_buttons)

    # Navigation row
    nav_buttons: list[InlineKeyboardButton] = []
    q_suffix = f":{query}" if query else ""

    if page > 1:
        nav_buttons.append(
            InlineKeyboardButton(text="◀️ Назад", callback_data=f"bm:page:{page - 1}{q_suffix}")
        )
    nav_buttons.append(
        InlineKeyboardButton(text=f"Стр. {page}/{total_pages}", callback_data="noop")
    )
    if page < total_pages:
        nav_buttons.append(
            InlineKeyboardButton(text="Вперёд ▶️", callback_data=f"bm:page:{page + 1}{q_suffix}")
        )
    builder.row(*nav_buttons)

    # Action row: Export all and Close
    builder.row(
        InlineKeyboardButton(text="📥 Экспорт всех (.md)", callback_data="bm:export"),
        InlineKeyboardButton(text="❌ Закрыть", callback_data="bm:close"),
    )

    return builder.as_markup()


def get_bookmark_detail_keyboard(bookmark_id: int, page: int) -> InlineKeyboardMarkup:
    """Build detail view keyboard with delete and back actions."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🗑️ Удалить", callback_data=f"bm:del:{bookmark_id}:{page}"),
        InlineKeyboardButton(text="↩️ К списку", callback_data=f"bm:page:{page}"),
    )
    return builder.as_markup()
