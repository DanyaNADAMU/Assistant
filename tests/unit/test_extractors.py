"""Unit tests for document and media extractors."""

import asyncio
import shutil
from pathlib import Path

import pytest

from assistant.adapters.extractors.audio import AudioExtractor, probe_audio_duration
from assistant.adapters.extractors.document import DocumentExtractor
from assistant.adapters.extractors.web import WebExtractor
from assistant.config import TaskCategory
from assistant.core.models.payload import InputPayload, PayloadKind
from assistant.core.models.result import ProcessingResult


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


@pytest.mark.asyncio
async def test_audio_extractor_real_audio_and_probe(tmp_path: Path) -> None:
    """Verify audio extractor processes audible files, measures duration, and normalizes."""
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("ffmpeg/ffprobe not installed in test environment")

    # Generate synthetic 1.5s sine audio
    wav_path = tmp_path / "test_sine.wav"
    cmd = [
        "ffmpeg",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=1000:duration=1.5",
        "-y",
        str(wav_path),
    ]
    proc = await asyncio.create_subprocess_exec(*cmd)
    await proc.communicate()
    assert wav_path.exists()

    # Test ffprobe probe
    duration = await probe_audio_duration(wav_path)
    assert duration is not None
    assert 1.4 <= duration <= 1.6

    # Test AudioExtractor processing
    extractor = AudioExtractor()
    payload = InputPayload(kind=PayloadKind.VOICE, file_path=wav_path)
    enriched = await extractor.extract(payload)

    assert enriched.mime_type == "audio/mp3"
    assert enriched.content_bytes is not None
    assert len(enriched.content_bytes) > 1024
    assert enriched.metadata.get("loudnorm_applied") is True
    assert "duration_seconds" in enriched.metadata
    assert enriched.metadata.get("is_silent") is not True


@pytest.mark.asyncio
async def test_audio_extractor_silence_detection(tmp_path: Path) -> None:
    """Verify audio extractor detects silence-only files."""
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg not installed in test environment")

    # Generate synthetic 1.0s pure silence
    silence_path = tmp_path / "silence.wav"
    cmd = [
        "ffmpeg",
        "-f",
        "lavfi",
        "-i",
        "anullsrc=r=44100:cl=mono:d=1",
        "-y",
        str(silence_path),
    ]
    proc = await asyncio.create_subprocess_exec(*cmd)
    await proc.communicate()
    assert silence_path.exists()

    extractor = AudioExtractor()
    payload = InputPayload(kind=PayloadKind.AUDIO, file_path=silence_path)
    enriched = await extractor.extract(payload)

    assert enriched.metadata.get("is_silent") is True


def test_audio_duration_formatting() -> None:
    """Verify ProcessingResult formats audio duration nicely into Telegram header."""
    res = ProcessingResult(
        category=TaskCategory.AUDIO_VIDEO,
        summary="Audio meeting overview",
        transcription="Hello team, let's start the sync.",
        key_takeaways=["Action item 1"],
        model_used="google/gemini-flash",
        audio_duration_seconds=102.5,  # 1 min 42 sec
    )
    msg = res.format_telegram_message()
    assert "🎙️ **Расшифровка (STT)** `[⏱ 01:42]`:" in msg
    assert "Hello team, let's start the sync." in msg
