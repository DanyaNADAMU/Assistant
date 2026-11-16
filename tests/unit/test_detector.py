"""Unit tests for CategoryDetector."""

from pathlib import Path

from summary_bot.config import TaskCategory
from summary_bot.core.models.payload import InputPayload, PayloadKind
from summary_bot.core.services.detector import CategoryDetector


def test_detect_pro_override() -> None:
    payload = InputPayload(kind=PayloadKind.TEXT, text="Hello world", is_pro=True)
    assert CategoryDetector.detect(payload) == TaskCategory.PRO


def test_detect_audio_streams() -> None:
    for kind in (PayloadKind.VOICE, PayloadKind.AUDIO, PayloadKind.VIDEO, PayloadKind.VIDEO_NOTE):
        payload = InputPayload(kind=kind, file_path=Path("test.mp4"))
        assert CategoryDetector.detect(payload) == TaskCategory.AUDIO_VIDEO


def test_detect_visual_streams() -> None:
    for kind in (PayloadKind.IMAGE, PayloadKind.STICKER, PayloadKind.GIF):
        payload = InputPayload(kind=kind, file_path=Path("test.jpg"))
        assert CategoryDetector.detect(payload) == TaskCategory.VISION


def test_detect_location() -> None:
    payload = InputPayload(kind=PayloadKind.LOCATION, latitude=55.75, longitude=37.61)
    assert CategoryDetector.detect(payload) == TaskCategory.MICRO


def test_detect_documents_and_urls() -> None:
    doc_payload = InputPayload(kind=PayloadKind.DOCUMENT, filename="report.pdf")
    url_payload = InputPayload(kind=PayloadKind.URL, url="https://example.com/article")
    assert CategoryDetector.detect(doc_payload) == TaskCategory.TEXT_DOCS
    assert CategoryDetector.detect(url_payload) == TaskCategory.TEXT_DOCS


def test_detect_micro_text_vs_long_text() -> None:
    short_text = InputPayload(kind=PayloadKind.TEXT, text="Привет! Как дела?")
    assert CategoryDetector.detect(short_text) == TaskCategory.MICRO

    long_text = InputPayload(kind=PayloadKind.TEXT, text="A" * 300)
    assert CategoryDetector.detect(long_text) == TaskCategory.TEXT_DOCS
