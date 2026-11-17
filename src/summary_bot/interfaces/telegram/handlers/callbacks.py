"""Telegram callback query handlers for interactive actions."""

import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from summary_bot.adapters.storage import preferences_repo
from summary_bot.core.services.context_store import context_store
from summary_bot.core.services.exporter import document_exporter
from summary_bot.core.services.runner import ResilientModelRunner
from summary_bot.core.services.telemetry import telemetry_service
from summary_bot.interfaces.telegram.keyboards import (
    get_export_keyboard,
    get_settings_keyboard,
    get_status_keyboard,
    get_summary_keyboard,
)

logger = logging.getLogger(__name__)
router = Router(name="callbacks")


@router.callback_query(F.data.startswith("act:"))
async def handle_summary_action(callback: CallbackQuery, runner: ResilientModelRunner) -> None:
    """Handle interactive post-summary action buttons."""
    if not callback.data or not callback.message or not isinstance(callback.message, Message):
        await callback.answer()
        return

    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.answer("Некорректная команда", show_alert=True)
        return

    _, cid, action = parts
    context = await context_store.get(cid)
    if not context:
        await callback.answer(
            "⚠️ Контекст сообщения устарел. Отправьте материал повторно для анализа.",
            show_alert=True,
        )
        return

    has_stt = bool(context.transcription)

    try:
        if action == "export":
            await callback.message.edit_reply_markup(reply_markup=get_export_keyboard(cid))
            await callback.answer()
            return

        if action == "orig":
            await callback.message.edit_text(
                context.original_text,
                parse_mode="Markdown",
                reply_markup=get_summary_keyboard(
                    cid, active_view="orig", has_transcription=has_stt
                ),
            )
            await callback.answer()
            return

        if action == "stt":
            if not context.transcription:
                await callback.answer("Транскрипт отсутствует", show_alert=True)
                return
            formatted_stt = (
                f"🎙️ **Полный транскрипт речи**:\n\n"
                f"{context.transcription.strip()}\n\n"
                f"—\n🤖 *{context.model_used}*"
            )
            # Clip if too long for a single edit
            if len(formatted_stt) > 4000:
                formatted_stt = formatted_stt[:3950] + "\n\n...[обрезано по лимиту Telegram]"

            await callback.message.edit_text(
                formatted_stt,
                parse_mode="Markdown",
                reply_markup=get_summary_keyboard(cid, active_view="stt", has_transcription=True),
            )
            await callback.answer()
            return

        # Handle refinement actions (tldr, actions, deep, trans)
        if action in context.views:
            await callback.message.edit_text(
                context.views[action],
                parse_mode="Markdown",
                reply_markup=get_summary_keyboard(
                    cid, active_view=action, has_transcription=has_stt
                ),
            )
            await callback.answer()
            return

        # Notify user that processing is happening
        await callback.answer("⏳ Анализирую и генерирую ответ...", show_alert=False)

        refined = await runner.refine(
            source_content=context.source_content,
            action=action,
            category=context.category,
        )

        match action:
            case "tldr":
                content = f"📌 **Краткая суть (TL;DR)**:\n\n{refined.strip()}"
            case "actions":
                content = f"📋 **Задачи и действия (Action Items)**:\n\n{refined.strip()}"
            case "deep":
                content = f"🔍 **Детальный разбор**:\n\n{refined.strip()}"
            case "trans":
                content = f"🌐 **Перевод (Translation)**:\n\n{refined.strip()}"
            case _:
                content = refined.strip()

        formatted_view = f"{content}\n\n—\n🤖 *{context.model_used}*"
        if len(formatted_view) > 4000:
            formatted_view = formatted_view[:3950] + "\n\n...[обрезано по лимиту Telegram]"

        context.views[action] = formatted_view

        await callback.message.edit_text(
            formatted_view,
            parse_mode="Markdown",
            reply_markup=get_summary_keyboard(cid, active_view=action, has_transcription=has_stt),
        )
    except TelegramBadRequest as exc:
        if "message is not modified" in str(exc).lower():
            await callback.answer()
        else:
            logger.warning("TelegramBadRequest in callback %s: %s", callback.data, exc)
            await callback.answer("Ошибка обновления сообщения", show_alert=True)
    except Exception as exc:
        logger.exception("Failed to handle callback %s: %s", callback.data, exc)
        await callback.answer(f"❌ Ошибка: {exc}", show_alert=True)


@router.callback_query(F.data.startswith("exp:"))
async def handle_document_export(callback: CallbackQuery, bot: Bot) -> None:
    """Generate and send downloadable document in selected format."""
    if not callback.data or not callback.message or not isinstance(callback.message, Message):
        await callback.answer()
        return

    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.answer("Некорректная команда", show_alert=True)
        return

    _, cid, fmt_str = parts
    context = await context_store.get(cid)
    if not context:
        await callback.answer(
            "⚠️ Контекст сообщения устарел. Отправьте материал повторно для анализа.",
            show_alert=True,
        )
        return

    try:
        await callback.answer("📄 Формирую файл документа...", show_alert=False)
        file_bytes, filename, _ = document_exporter.export(context, fmt_str)
        doc = BufferedInputFile(file_bytes, filename=filename)
        await bot.send_document(
            chat_id=callback.message.chat.id,
            document=doc,
            caption=(
                f"📥 **Экспорт документа** (`{fmt_str.upper()}`)\n\n"
                f"• ID: `{context.cid}`\n"
                f"• Модель: `{context.model_used or 'OpenRouter'}`\n"
                f"• Байт: `{len(file_bytes):,}`"
            ),
            parse_mode="Markdown",
        )
    except Exception as exc:
        logger.exception("Failed to export document %s in format %s: %s", cid, fmt_str, exc)
        await callback.answer(f"❌ Ошибка экспорта: {exc}", show_alert=True)


@router.callback_query(F.data.startswith("pref:"))
async def handle_preference_toggle(callback: CallbackQuery) -> None:
    """Handle interactive user preferences toggle buttons."""
    if not callback.data or not callback.message or not isinstance(callback.message, Message):
        await callback.answer()
        return

    user_id = callback.from_user.id
    username = callback.from_user.username
    setting = callback.data.removeprefix("pref:")

    prefs = await preferences_repo.get(user_id)
    toast = ""

    match setting:
        case "lang":
            prefs.language = prefs.next_language()
            toast = f"Язык изменен: {prefs.language.label}"
        case "depth":
            prefs.depth = prefs.next_depth()
            toast = f"Глубина изменена: {prefs.depth.label}"
        case "format":
            prefs.format = prefs.next_format()
            toast = f"Формат изменен: {prefs.format.label}"
        case "actions":
            prefs.include_action_items = not prefs.include_action_items
            status = "включен" if prefs.include_action_items else "выключен"
            toast = f"Список задач {status}"
        case "reset":
            prefs = await preferences_repo.reset(user_id)
            toast = "Настройки сброшены по умолчанию"
        case _:
            await callback.answer("Неизвестный параметр")
            return

    if setting != "reset":
        await preferences_repo.save(prefs)

    card_text = prefs.format_settings_card(username=username)
    markup = get_settings_keyboard(prefs)

    try:
        await callback.message.edit_text(card_text, parse_mode="Markdown", reply_markup=markup)
    except TelegramBadRequest as err:
        if "message is not modified" not in str(err).lower():
            logger.warning("Failed to edit settings message: %s", err)

    await callback.answer(toast)


@router.callback_query(F.data.startswith("status:"))
async def handle_status_action(callback: CallbackQuery) -> None:
    """Handle status card interactive actions (refresh, navigate to settings)."""
    if not callback.data or not callback.message or not isinstance(callback.message, Message):
        await callback.answer()
        return

    action = callback.data.removeprefix("status:")

    if action == "refresh":
        snapshot = await telemetry_service.collect()
        report = snapshot.format_telegram_report()
        markup = get_status_keyboard()
        try:
            await callback.message.edit_text(report, parse_mode="Markdown", reply_markup=markup)
            await callback.answer("Данные обновлены ✅")
        except TelegramBadRequest as err:
            if "message is not modified" in str(err).lower():
                await callback.answer("Данные актуальны ✅")
            else:
                logger.warning("Failed to refresh status message: %s", err)
                await callback.answer()
        return

    if action == "settings":
        user_id = callback.from_user.id
        username = callback.from_user.username
        prefs = await preferences_repo.get(user_id)
        card_text = prefs.format_settings_card(username=username)
        markup = get_settings_keyboard(prefs)
        try:
            await callback.message.edit_text(card_text, parse_mode="Markdown", reply_markup=markup)
        except TelegramBadRequest as err:
            if "message is not modified" not in str(err).lower():
                logger.warning("Failed to open settings: %s", err)
        await callback.answer()
        return
