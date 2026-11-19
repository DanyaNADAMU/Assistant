"""Telegram handlers for personal bookmarks and knowledge archive."""

import contextlib
import logging
from datetime import UTC, datetime
from typing import cast

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from summary_bot.adapters.storage import bookmarks_repo
from summary_bot.core.models.bookmark import BookmarkItem
from summary_bot.core.services.context_store import context_store
from summary_bot.interfaces.telegram.keyboards import (
    get_bookmark_detail_keyboard,
    get_bookmarks_page_keyboard,
    get_summary_keyboard,
)

logger = logging.getLogger(__name__)
router = Router(name="bookmarks")

PAGE_SIZE = 5


def _extract_user_id(event: Message | CallbackQuery) -> int:
    """Safely extract user ID as a native integer."""
    try:
        from_user = getattr(event, "from_user", None)
        if from_user is not None and getattr(from_user, "id", None) is not None:
            return int(from_user.id)
        chat = getattr(event, "chat", None)
        if chat is not None and getattr(chat, "id", None) is not None:
            return int(chat.id)
        msg = getattr(event, "message", None)
        if msg is not None:
            msg_chat = getattr(msg, "chat", None)
            if msg_chat is not None and getattr(msg_chat, "id", None) is not None:
                return int(msg_chat.id)
        return 0
    except (TypeError, ValueError):
        return 0


def _format_page_text(items: list[BookmarkItem], page: int, total_count: int, query: str | None = None) -> str:
    """Format markdown text for a paginated list of bookmarks."""
    total_pages = max(1, (total_count + PAGE_SIZE - 1) // PAGE_SIZE)
    header = "📚 **Ваша библиотека закладок**"
    if query:
        header += f" (поиск: *{query}*)"
    header += f" — {total_count} шт. [Стр. {page}/{total_pages}]\n\n"

    items_text = "".join(item.format_preview(index=(page - 1) * PAGE_SIZE + idx + 1) for idx, item in enumerate(items))
    footer = "\n_Нажмите номер кнопки ниже, чтобы открыть полное саммари:_"
    return header + items_text + footer


@router.message(Command("saved", "bookmarks"))
async def handle_saved_command(message: Message) -> None:
    """Display user's saved bookmarks with pagination and search."""
    user_id = _extract_user_id(message)

    # Optional search query from command arguments
    query: str | None = None
    if message.text:
        parts = message.text.strip().split(maxsplit=1)
        if len(parts) > 1 and parts[1].strip():
            query = parts[1].strip()

    items, total_count = await bookmarks_repo.list_bookmarks(user_id=user_id, page=1, page_size=PAGE_SIZE, query=query)

    if not items:
        if query:
            await message.reply(
                f"🔍 По запросу *«{query}»* ничего не найдено в ваших закладках.\n"
                f"Используйте `/saved` без аргументов для просмотра всей библиотеки.",
                parse_mode="Markdown",
            )
        else:
            await message.reply(
                "⭐ **Ваша библиотека закладок пуста**\n\n"
                "Чтобы сохранить любое саммари в персональный архив, нажмите кнопку "
                "**☆ В закладки** под сообщением с результатом анализа.",
                parse_mode="Markdown",
            )
        return

    total_pages = max(1, (total_count + PAGE_SIZE - 1) // PAGE_SIZE)
    bookmark_ids = [item.id for item in items if item.id is not None]
    text = _format_page_text(items, page=1, total_count=total_count, query=query)
    markup = get_bookmarks_page_keyboard(
        bookmark_ids=bookmark_ids,
        page=1,
        total_pages=total_pages,
        query=query,
    )
    await message.reply(text, parse_mode="Markdown", reply_markup=markup, disable_web_page_preview=True)


@router.callback_query(F.data.startswith("bm:toggle:"))
async def handle_bookmark_toggle(callback: CallbackQuery) -> None:
    """Toggle bookmark status for an active summary card."""
    if not callback.data or not callback.message:
        await callback.answer()
        return

    message = cast("Message", callback.message)
    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.answer("Некорректная команда", show_alert=True)
        return

    _, _, cid = parts
    user_id = _extract_user_id(callback)

    context = await context_store.get(cid)
    if not context:
        await callback.answer(
            "⚠️ Контекст сообщения устарел. Отправьте материал повторно для анализа.",
            show_alert=True,
        )
        return

    is_currently_bm = await bookmarks_repo.is_bookmarked(user_id, cid)

    if is_currently_bm:
        await bookmarks_repo.remove_bookmark_by_context(user_id, cid)
        await callback.answer("🗑️ Удалено из закладок")
        new_is_bm = False
    else:
        item = BookmarkItem(
            user_id=user_id,
            context_id=cid,
            title=context.title,
            source_url=context.source_url,
            summary_text=context.summary,
            takeaways=context.key_takeaways,
            category=context.category.value,
        )
        await bookmarks_repo.add_bookmark(item)
        await callback.answer("⭐ Сохранено в закладки!")
        new_is_bm = True

    has_stt = bool(context.transcription)
    # Refresh keyboard with new bookmark state
    with contextlib.suppress(Exception):
        await message.edit_reply_markup(
            reply_markup=get_summary_keyboard(
                cid=cid,
                active_view="orig",
                has_transcription=has_stt,
                is_bookmarked=new_is_bm,
            )
        )


@router.callback_query(F.data.startswith("bm:page:"))
async def handle_bookmark_page(callback: CallbackQuery) -> None:
    """Handle pagination navigation in bookmarks list."""
    if not callback.data or not callback.message:
        await callback.answer()
        return

    message = cast("Message", callback.message)
    parts = callback.data.split(":")
    # Format: bm:page:<page> or bm:page:<page>:<query>
    page = int(parts[2]) if len(parts) > 2 else 1
    query = parts[3] if len(parts) > 3 and parts[3] else None
    user_id = _extract_user_id(callback)

    items, total_count = await bookmarks_repo.list_bookmarks(user_id=user_id, page=page, page_size=PAGE_SIZE, query=query)
    total_pages = max(1, (total_count + PAGE_SIZE - 1) // PAGE_SIZE)
    bookmark_ids = [item.id for item in items if item.id is not None]

    text = _format_page_text(items, page=page, total_count=total_count, query=query)
    markup = get_bookmarks_page_keyboard(
        bookmark_ids=bookmark_ids,
        page=page,
        total_pages=total_pages,
        query=query,
    )

    with contextlib.suppress(Exception):
        await message.edit_text(
            text,
            parse_mode="Markdown",
            reply_markup=markup,
            disable_web_page_preview=True,
        )
    await callback.answer()


@router.callback_query(F.data.startswith("bm:open:"))
async def handle_bookmark_open(callback: CallbackQuery) -> None:
    """Open full view of a saved bookmark."""
    if not callback.data or not callback.message:
        await callback.answer()
        return

    message = cast("Message", callback.message)
    parts = callback.data.split(":")
    if len(parts) < 4:
        await callback.answer("Ошибка параметров", show_alert=True)
        return

    bookmark_id = int(parts[2])
    page = int(parts[3])
    user_id = _extract_user_id(callback)

    item = await bookmarks_repo.get_bookmark(user_id, bookmark_id)
    if not item:
        await callback.answer("Закладка не найдена или была удалена", show_alert=True)
        return

    text = item.format_full()
    markup = get_bookmark_detail_keyboard(bookmark_id=bookmark_id, page=page)

    with contextlib.suppress(Exception):
        await message.edit_text(
            text,
            parse_mode="Markdown",
            reply_markup=markup,
            disable_web_page_preview=True,
        )
    await callback.answer()


@router.callback_query(F.data.startswith("bm:del:"))
async def handle_bookmark_delete(callback: CallbackQuery) -> None:
    """Delete a saved bookmark and return to list."""
    if not callback.data or not callback.message:
        await callback.answer()
        return

    message = cast("Message", callback.message)
    parts = callback.data.split(":")
    if len(parts) < 4:
        await callback.answer("Ошибка параметров", show_alert=True)
        return

    bookmark_id = int(parts[2])
    page = int(parts[3])
    user_id = _extract_user_id(callback)

    await bookmarks_repo.remove_bookmark(user_id, bookmark_id)
    await callback.answer("🗑️ Закладка удалена")

    # Refresh page
    items, total_count = await bookmarks_repo.list_bookmarks(user_id=user_id, page=page, page_size=PAGE_SIZE)
    if not items and page > 1:
        page -= 1
        items, total_count = await bookmarks_repo.list_bookmarks(user_id=user_id, page=page, page_size=PAGE_SIZE)

    if not items:
        await message.edit_text(
            "⭐ **Ваша библиотека закладок пуста**\n\n"
            "Чтобы сохранить любое саммари в персональный архив, нажмите кнопку "
            "**☆ В закладки** под сообщением с результатом анализа.",
            parse_mode="Markdown",
        )
        return

    total_pages = max(1, (total_count + PAGE_SIZE - 1) // PAGE_SIZE)
    bookmark_ids = [item.id for item in items if item.id is not None]
    text = _format_page_text(items, page=page, total_count=total_count)
    markup = get_bookmarks_page_keyboard(
        bookmark_ids=bookmark_ids,
        page=page,
        total_pages=total_pages,
    )
    await message.edit_text(text, parse_mode="Markdown", reply_markup=markup, disable_web_page_preview=True)


@router.callback_query(F.data == "bm:export")
async def handle_bookmark_export(callback: CallbackQuery) -> None:
    """Export all user bookmarks into a clean downloadable Markdown document."""
    if not callback.message:
        await callback.answer()
        return

    message = cast("Message", callback.message)
    user_id = _extract_user_id(callback)
    items = await bookmarks_repo.get_all_bookmarks(user_id)

    if not items:
        await callback.answer("У вас нет сохранённых закладок для экспорта", show_alert=True)
        return

    now_str = datetime.now(UTC).strftime("%d.%m.%Y %H:%M UTC")
    lines: list[str] = [
        "# Моя библиотека закладок — SummaryBot",
        f"*Экспортировано: {now_str}*",
        f"*Всего закладок: {len(items)}*",
        "",
        "---",
        "",
    ]

    for idx, item in enumerate(items, start=1):
        lines.append(f"## {idx}. {item.title}")
        if item.source_url:
            lines.append(f"- **Источник:** [{item.source_url}]({item.source_url})")
        lines.append(f"- **Дата сохранения:** {item.created_at.strftime('%d.%m.%Y %H:%M UTC')}")
        lines.append(f"- **Категория:** `{item.category}`")
        lines.append("")
        lines.append("### Краткое содержание:")
        lines.append(item.summary_text)
        lines.append("")
        if item.takeaways:
            lines.append("### Главные мысли:")
            for t in item.takeaways:
                lines.append(f"- {t}")
            lines.append("")
        lines.append("---")
        lines.append("")

    doc_content = "\n".join(lines)
    file_bytes = doc_content.encode("utf-8")
    filename = f"summarybot_bookmarks_{datetime.now(UTC).strftime('%Y%m%d_%H%M')}.md"
    input_file = BufferedInputFile(file_bytes, filename=filename)

    await message.answer_document(
        document=input_file,
        caption=f"📚 Экспорт вашей библиотеки закладок ({len(items)} шт.) в формате Markdown.",
    )
    await callback.answer("✅ Экспорт готов!")


@router.callback_query(F.data == "bm:close")
async def handle_bookmark_close(callback: CallbackQuery) -> None:
    """Close bookmarks browser message."""
    if callback.message:
        message = cast("Message", callback.message)
        with contextlib.suppress(Exception):
            await message.delete()
    await callback.answer()


@router.callback_query(F.data == "noop")
async def handle_noop(callback: CallbackQuery) -> None:
    """No-operation handler for decorative buttons."""
    await callback.answer()
