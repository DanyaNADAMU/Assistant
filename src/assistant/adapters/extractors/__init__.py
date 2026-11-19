"""Extractors adapters exports."""

from assistant.adapters.extractors.audio import AudioExtractor
from assistant.adapters.extractors.document import DocumentExtractor
from assistant.adapters.extractors.vision import VisionExtractor
from assistant.adapters.extractors.web import WebExtractor

__all__ = ["AudioExtractor", "DocumentExtractor", "VisionExtractor", "WebExtractor"]
