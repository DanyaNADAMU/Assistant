"""Telegram bot runner and dispatcher initialization."""

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from summary_bot.adapters.extractors.audio import AudioExtractor
from summary_bot.adapters.extractors.document import DocumentExtractor
from summary_bot.adapters.extractors.vision import VisionExtractor
from summary_bot.adapters.extractors.web import WebExtractor
from summary_bot.adapters.openrouter.client import OpenRouterClient
from summary_bot.adapters.storage import response_cache
from summary_bot.config import Settings, settings
from summary_bot.core.services.batch import BatchSummarizer
from summary_bot.core.services.runner import ResilientModelRunner
from summary_bot.interfaces.telegram.handlers.callbacks import router as callbacks_router
from summary_bot.interfaces.telegram.handlers.commands import router as commands_router
from summary_bot.interfaces.telegram.handlers.media import router as media_router

logger = logging.getLogger(__name__)


def create_dispatcher(
    runner: ResilientModelRunner,
    batch_summarizer: BatchSummarizer | None = None,
) -> Dispatcher:
    """Create and configure aiogram Dispatcher with registered dependency workflow."""
    dp = Dispatcher()

    if batch_summarizer is None:
        batch_summarizer = BatchSummarizer(
            runner=runner,
            gateway=runner._gateway,
            settings=runner._settings,
        )

    # Pass dependencies to all handler calls
    dp["runner"] = runner
    dp["batch_summarizer"] = batch_summarizer

    # Register routers (commands must be first to intercept /start, /help, /models)
    dp.include_router(commands_router)
    dp.include_router(callbacks_router)
    dp.include_router(media_router)

    return dp


async def start_telegram_bot(custom_settings: Settings | None = None) -> None:
    """Start polling loop for SummaryBot Telegram bot."""
    active_settings = custom_settings or settings

    token = active_settings.effective_bot_token
    if not token:
        raise ValueError("Neither TELEGRAM_BOT_TOKEN nor TEST_TELEGRAM_BOT_TOKEN is configured.")

    bot = Bot(
        token=token,
        default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN),
    )

    gateway = OpenRouterClient(settings=active_settings)
    extractors = [AudioExtractor(), DocumentExtractor(), VisionExtractor(), WebExtractor()]
    runner = ResilientModelRunner(
        gateway=gateway,
        settings=active_settings,
        extractors=extractors,
        cache=response_cache,
    )
    batch_summarizer = BatchSummarizer(
        runner=runner,
        gateway=gateway,
        settings=active_settings,
    )

    dp = create_dispatcher(runner=runner, batch_summarizer=batch_summarizer)

    logger.info("Starting Telegram Bot polling loop...")
    try:
        # Drop pending updates to avoid backlog on restart
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        logger.info("Telegram Bot session closed.")


def run_bot() -> None:
    """Synchronous entry point for running the Telegram bot."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    asyncio.run(start_telegram_bot())


if __name__ == "__main__":
    run_bot()
