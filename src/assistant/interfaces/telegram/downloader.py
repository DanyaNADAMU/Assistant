"""Telegram file downloader with size limits and temporary file management."""

import contextlib
import logging
import tempfile
from collections.abc import AsyncIterator
from pathlib import Path

from aiogram import Bot

logger = logging.getLogger(__name__)


class FileTooLargeError(Exception):
    """Raised when incoming media exceeds max allowed download size."""


@contextlib.asynccontextmanager
async def download_telegram_file(
    bot: Bot,
    file_id: str,
    max_size_bytes: int,
    custom_suffix: str = ".bin",
) -> AsyncIterator[Path]:
    """Download a file from Telegram API into a safe temporary file."""
    file_info = await bot.get_file(file_id)

    if file_info.file_size and file_info.file_size > max_size_bytes:
        size_mb = file_info.file_size / (1024 * 1024)
        max_mb = max_size_bytes / (1024 * 1024)
        raise FileTooLargeError(
            f"Размер файла ({size_mb:.1f} MB) превышает установленный лимит ({max_mb:.1f} MB)."
        )

    if not file_info.file_path:
        raise ValueError("Telegram API returned empty file_path")

    # Determine file extension from telegram file path if not custom
    ext = Path(file_info.file_path).suffix or custom_suffix

    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as temp_dest:
        dest_path = Path(temp_dest.name)

    try:
        logger.debug("Downloading file %s to %s", file_id, dest_path)
        await bot.download_file(file_info.file_path, destination=dest_path)
        yield dest_path
    finally:
        with contextlib.suppress(OSError):
            dest_path.unlink(missing_ok=True)
            logger.debug("Cleaned up temporary download: %s", dest_path)
