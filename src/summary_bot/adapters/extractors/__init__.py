"""Extractors adapters exports."""

from summary_bot.adapters.extractors.audio import AudioExtractor
from summary_bot.adapters.extractors.document import DocumentExtractor
from summary_bot.adapters.extractors.web import WebExtractor

__all__ = ["AudioExtractor", "DocumentExtractor", "WebExtractor"]
