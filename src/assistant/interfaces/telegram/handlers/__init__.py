"""Telegram handlers exports."""

from assistant.interfaces.telegram.handlers.callbacks import router as callbacks_router
from assistant.interfaces.telegram.handlers.commands import router as commands_router
from assistant.interfaces.telegram.handlers.generation import router as generation_router
from assistant.interfaces.telegram.handlers.inline import router as inline_router
from assistant.interfaces.telegram.handlers.media import router as media_router

__all__ = [
    "callbacks_router",
    "commands_router",
    "generation_router",
    "inline_router",
    "media_router",
]
