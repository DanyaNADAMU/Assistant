"""Unit tests for document and media extractors."""

import pytest

from summary_bot.adapters.extractors.audio import AudioExtractor
from summary_bot.adapters.extractors.document import DocumentExtractor
from summary_bot.adapters.extractors.web import WebExtractor
from summary_bot.core.models.payload import InputPayload, PayloadKind


@pytest.mark.asyncio
async def test_document_extractor_txt() -> None:
    extractor = DocumentExtractor()
    payload = InputPayload(
        kind=PayloadKind.DOCUMENT,
        filename="notes.txt",
        content_bytes="Ключевые пункты проекта:\n1. Ядро\n2. CLI\n3. Бот".encode(),
    )

    assert await extractor.can_handle(payload) is True
    enriched = await extractor.extract(payload)
    assert enriched.text is not None
    assert "Ядро" in enriched.text
    assert enriched.kind == PayloadKind.TEXT


@pytest.mark.asyncio
async def test_audio_extractor_handles_media_kinds() -> None:
    extractor = AudioExtractor()
    for kind in (PayloadKind.VIDEO, PayloadKind.VIDEO_NOTE, PayloadKind.VOICE, PayloadKind.AUDIO):
        payload = InputPayload(kind=kind)
        assert await extractor.can_handle(payload) is True

    text_payload = InputPayload(kind=PayloadKind.TEXT)
    assert await extractor.can_handle(text_payload) is False


@pytest.mark.asyncio
async def test_web_extractor_handles_urls() -> None:
    extractor = WebExtractor()
    url_payload = InputPayload(kind=PayloadKind.URL, url="https://example.com/post")
    assert await extractor.can_handle(url_payload) is True

    text_url_payload = InputPayload(kind=PayloadKind.TEXT, text="https://example.com/post")
    assert await extractor.can_handle(text_url_payload) is True

    plain_text = InputPayload(kind=PayloadKind.TEXT, text="Just plain text without url")
    assert await extractor.can_handle(plain_text) is False
