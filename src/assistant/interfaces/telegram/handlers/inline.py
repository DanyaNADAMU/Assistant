"""Telegram inline query handler for search and instant summary sharing."""

import contextlib
import hashlib
import logging
import re
from urllib.parse import urlparse

from aiogram import Router
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQuery,
    InlineQueryResultArticle,
    InlineQueryResultUnion,
    InputTextMessageContent,
)

from assistant.adapters.storage import response_cache
from assistant.core.models.payload import InputPayload, PayloadKind
from assistant.core.ports.cache import CachedSummaryItem
from assistant.core.services.runner import ResilientModelRunner

logger = logging.getLogger(__name__)

router = Router(name="inline_query")

URL_PATTERN = re.compile(r"https?://[^\s]+", re.IGNORECASE)


def _clean_url(raw: str) -> str:
    """Strip trailing punctuation from URL."""
    return raw.rstrip(".,!?;:)>]}\"'")


def _is_valid_url(candidate: str) -> bool:
    try:
        parsed = urlparse(candidate)
        return bool(parsed.scheme in ("http", "https") and parsed.netloc)
    except Exception:
        return False


def _format_cached_article_content(item: CachedSummaryItem, bot_username: str) -> str:
    """Format full telegram message text for a cached summary item."""
    res = item.to_processing_result()
    msg = res.format_telegram_message()
    footer = f"\n\n🤖 *Отправлено через* @{bot_username}"
    return msg + footer


def _build_inline_keyboard(
    bot_username: str, source_url: str | None = None
) -> InlineKeyboardMarkup:
    """Create action buttons for inline results."""
    buttons: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []

    if source_url:
        row.append(InlineKeyboardButton(text="🔗 Источник", url=source_url))

    row.append(
        InlineKeyboardButton(
            text="🤖 Assistant",
            url=f"https://t.me/{bot_username}",
        )
    )
    buttons.append(row)
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.inline_query()
async def handle_inline_query(
    inline_query: InlineQuery,
    runner: ResilientModelRunner,
) -> None:
    """Process incoming inline queries from any Telegram chat."""
    query = inline_query.query.strip()
    results: list[InlineQueryResultUnion] = []

    try:
        bot = inline_query.bot
        if bot is None:
            return

        me = await bot.get_me()
        bot_username = me.username or "Assistant"

        # Check if the query contains a URL
        url_match = URL_PATTERN.search(query)
        target_url = _clean_url(url_match.group(0)) if url_match else None

        if target_url and _is_valid_url(target_url):
            # Check if this URL is already in cache
            payload = InputPayload(kind=PayloadKind.URL, url=target_url)
            content_hash = payload.compute_content_hash()
            cache = runner._cache or response_cache
            cached_result = await cache.get_summary(
                content_hash=content_hash,
                is_pro=False,
            )

            if cached_result:
                # Article 1: Full cached summary
                formatted_text = (
                    cached_result.format_telegram_message()
                    + f"\n\n🤖 *Отправлено через* @{bot_username}"
                )
                article_summary = InlineQueryResultArticle(
                    id=f"url_sum_{content_hash[:12]}",
                    title=f"⚡ Саммари: {target_url[:50]}",
                    description=cached_result.summary[:120].strip() + "...",
                    input_message_content=InputTextMessageContent(
                        message_text=formatted_text,
                        parse_mode="Markdown",
                    ),
                    reply_markup=_build_inline_keyboard(bot_username, source_url=target_url),
                )
                results.append(article_summary)

                # Article 2: Key takeaways if present
                if cached_result.key_takeaways:
                    takeaways_text = (
                        f"💡 **Главные мысли из ссылки**:\n{target_url}\n\n"
                        + "\n".join(f"• {t.strip()}" for t in cached_result.key_takeaways)
                        + f"\n\n🤖 *Отправлено через* @{bot_username}"
                    )
                    article_takeaways = InlineQueryResultArticle(
                        id=f"url_take_{content_hash[:12]}",
                        title="📋 Главные тезисы",
                        description=" • ".join(cached_result.key_takeaways)[:120],
                        input_message_content=InputTextMessageContent(
                            message_text=takeaways_text,
                            parse_mode="Markdown",
                        ),
                        reply_markup=_build_inline_keyboard(bot_username, source_url=target_url),
                    )
                    results.append(article_takeaways)
            else:
                # URL is not yet in cache -> offer to summarize
                safe_url = target_url
                invite_text = (
                    f"✨ **Запрос на саммаризацию**:\n{safe_url}\n\n"
                    f"🤖 [Открыть в @{bot_username}](https://t.me/{bot_username}?start=sum) "
                    "для мгновенного глубокого анализа, тезисов и экспорта в Markdown/HTML."
                )
                article_req = InlineQueryResultArticle(
                    id=f"req_{hashlib.sha256(safe_url.encode()).hexdigest()[:12]}",
                    title=f"✨ Саммаризировать: {safe_url[:45]}...",
                    description="Нажмите для отправки карточки с переходом к анализу",
                    input_message_content=InputTextMessageContent(
                        message_text=invite_text,
                        parse_mode="Markdown",
                    ),
                    reply_markup=_build_inline_keyboard(bot_username, source_url=safe_url),
                )
                results.append(article_req)

        elif query:
            # Keyword search across cached summaries
            matched_items = await response_cache.search_summaries(query=query, limit=10)
            if matched_items:
                for item in matched_items:
                    formatted_content = _format_cached_article_content(item, bot_username)
                    preview_desc = (
                        item.summary[:100].replace("\n", " ").strip() + "..."
                        if len(item.summary) > 100
                        else item.summary
                    )
                    article = InlineQueryResultArticle(
                        id=f"search_{item.content_hash[:12]}",
                        title=f"📄 {item.category.capitalize()} ({item.created_at[:10]})",
                        description=preview_desc,
                        input_message_content=InputTextMessageContent(
                            message_text=formatted_content,
                            parse_mode="Markdown",
                        ),
                        reply_markup=_build_inline_keyboard(bot_username),
                    )
                    results.append(article)
            else:
                # No matches found
                empty_article = InlineQueryResultArticle(
                    id="search_empty",
                    title=f"🔍 Ничего не найдено по запросу: '{query[:30]}'",
                    description="Отправьте ссылку боту напрямую, чтобы создать новое саммари",
                    input_message_content=InputTextMessageContent(
                        message_text=(
                            f"🔍 По запросу `{query}` в кэше ничего не найдено.\n\n"
                            f"🤖 Перейдите в @{bot_username} и отправьте ссылку или документ!"
                        ),
                        parse_mode="Markdown",
                    ),
                    reply_markup=_build_inline_keyboard(bot_username),
                )
                results.append(empty_article)

        else:
            # Empty query: show recent summaries + usage guide
            recent_items = await response_cache.search_summaries(query="", limit=5)
            for item in recent_items:
                formatted_content = _format_cached_article_content(item, bot_username)
                preview_desc = (
                    item.summary[:100].replace("\n", " ").strip() + "..."
                    if len(item.summary) > 100
                    else item.summary
                )
                article = InlineQueryResultArticle(
                    id=f"recent_{item.content_hash[:12]}",
                    title=f"🕒 Недавнее: {item.category.capitalize()} ({item.created_at[:10]})",
                    description=preview_desc,
                    input_message_content=InputTextMessageContent(
                        message_text=formatted_content,
                        parse_mode="Markdown",
                    ),
                    reply_markup=_build_inline_keyboard(bot_username),
                )
                results.append(article)

            # Help guide article
            help_article = InlineQueryResultArticle(
                id="inline_guide",
                title="💡 Как работает @Assistant в любом чате?",
                description="Введите ссылку (https://...) или слово для поиска по сохранённым саммари",
                input_message_content=InputTextMessageContent(
                    message_text=(
                        "💡 **Как использовать Assistant в любых чатах:**\n\n"
                        "1. **Проверка ссылки**: `@Assistant <url>` — если ссылка уже "
                        "анализировалась, саммари отправится мгновенно!\n"
                        "2. **Поиск по истории**: `@Assistant <слово>` — находите ваши "
                        "сохранённые выжимки и делитесь ими в один клик.\n"
                        "3. **Анализ новых материалов**: отправьте ссылку или файл напрямую в диалог с ботом.\n\n"
                        f"🤖 Запустите @{bot_username} для расширенных возможностей!"
                    ),
                    parse_mode="Markdown",
                ),
                reply_markup=_build_inline_keyboard(bot_username),
            )
            results.append(help_article)

        await inline_query.answer(
            results=results,
            cache_time=5,
            is_personal=True,
        )
    except Exception as exc:
        logger.exception("Error processing inline query '%s': %s", query, exc)
        with contextlib.suppress(Exception):
            await inline_query.answer(
                results=[],
                cache_time=2,
                is_personal=True,
            )
