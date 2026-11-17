"""Telegram handlers exports."""

from summary_bot.interfaces.telegram.handlers.callbacks import router as callbacks_router
from summary_bot.interfaces.telegram.handlers.commands import router as commands_router
from summary_bot.interfaces.telegram.handlers.media import router as media_router

__all__ = ["callbacks_router", "commands_router", "media_router"]
