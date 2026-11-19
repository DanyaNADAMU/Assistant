"""Unit tests for VisionExtractor and multimodal image pipeline."""

import io
from unittest.mock import MagicMock

import pytest
from PIL import Image

from assistant.adapters.extractors.document import DocumentExtractor
from assistant.adapters.extractors.vision import MAX_IMAGE_DIMENSION, VisionExtractor
from assistant.core.models.payload import InputPayload, PayloadKind


def create_test_image_bytes(
    width: int,
    height: int,
    color: tuple[int, int, int] = (255, 0, 0),
    fmt: str = "JPEG",
    mode: str = "RGB",
) -> bytes:
    """Helper to generate in-memory test image bytes."""
    img = Image.new(mode, (width, height), color=color)  # type: ignore[arg-type]
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


@pytest.mark.asyncio
async def test_vision_extractor_can_handle() -> None:
    extractor = VisionExtractor()

    # Direct visual streams
    assert await extractor.can_handle(InputPayload(kind=PayloadKind.IMAGE)) is True
    assert await extractor.can_handle(InputPayload(kind=PayloadKind.STICKER)) is True
    assert await extractor.can_handle(InputPayload(kind=PayloadKind.GIF)) is True

    # Image uploaded as document
    assert (
        await extractor.can_handle(
            InputPayload(kind=PayloadKind.DOCUMENT, filename="screenshot.png")
        )
        is True
    )
    assert (
        await extractor.can_handle(InputPayload(kind=PayloadKind.DOCUMENT, mime_type="image/jpeg"))
        is True
    )

    # Text documents and text
    assert (
        await extractor.can_handle(InputPayload(kind=PayloadKind.DOCUMENT, filename="report.pdf"))
        is False
    )
    assert await extractor.can_handle(InputPayload(kind=PayloadKind.TEXT, text="hello")) is False


@pytest.mark.asyncio
async def test_vision_extractor_normalizes_and_resizes() -> None:
    extractor = VisionExtractor()

    # Create oversized 3000x1500 image
    raw_bytes = create_test_image_bytes(3000, 1500, fmt="JPEG")
    payload = InputPayload(
        kind=PayloadKind.IMAGE,
        content_bytes=raw_bytes,
        mime_type="image/jpeg",
    )

    processed = await extractor.extract(payload)

    assert processed.kind == PayloadKind.IMAGE
    assert processed.content_bytes is not None
    assert processed.metadata["original_dimensions"] == "3000x1500"
    assert processed.metadata["image_width"] == MAX_IMAGE_DIMENSION
    assert processed.metadata["image_height"] == int(1500 * (MAX_IMAGE_DIMENSION / 3000))

    # Verify output bytes are valid image loadable by Pillow
    with Image.open(io.BytesIO(processed.content_bytes)) as result_img:
        assert result_img.size == (2048, 1024)


@pytest.mark.asyncio
async def test_vision_extractor_rgba_to_rgb() -> None:
    extractor = VisionExtractor()

    # RGBA image with alpha channel
    raw_bytes = create_test_image_bytes(200, 200, fmt="PNG", mode="RGBA")
    payload = InputPayload(
        kind=PayloadKind.IMAGE,
        content_bytes=raw_bytes,
        mime_type="image/png",
    )

    processed = await extractor.extract(payload)
    assert processed.mime_type in ("image/png", "image/jpeg")
    assert processed.content_bytes is not None


@pytest.mark.asyncio
async def test_document_extractor_rejects_images() -> None:
    doc_extractor = DocumentExtractor()

    # Image files must not be intercepted by DocumentExtractor
    assert (
        await doc_extractor.can_handle(
            InputPayload(kind=PayloadKind.DOCUMENT, filename="diagram.png")
        )
        is False
    )
    assert (
        await doc_extractor.can_handle(
            InputPayload(kind=PayloadKind.DOCUMENT, mime_type="image/jpeg")
        )
        is False
    )
    assert (
        await doc_extractor.can_handle(
            InputPayload(kind=PayloadKind.DOCUMENT, filename="notes.pdf")
        )
        is True
    )


@pytest.mark.asyncio
async def test_document_extractor_scanned_pdf_fallback() -> None:
    doc_extractor = DocumentExtractor()

    # Mock pypdf reader that has 0 text but contains embedded page images
    mock_image = MagicMock()
    mock_image.name = "page1_img.png"
    mock_image.data = b"\x89PNG\r\n\x1a\nfakeimagebytes"

    mock_page = MagicMock()
    mock_page.extract_text.return_value = ""  # Scanned PDF: no text layer
    mock_page.images = [mock_image]

    # Patch PdfReader in test
    import assistant.adapters.extractors.document as doc_mod

    orig_reader = doc_mod.PdfReader
    try:
        mock_reader_cls = MagicMock()
        mock_reader_instance = MagicMock()
        mock_reader_instance.pages = [mock_page]
        mock_reader_cls.return_value = mock_reader_instance
        doc_mod.PdfReader = mock_reader_cls

        payload = InputPayload(
            kind=PayloadKind.DOCUMENT,
            filename="scanned_contract.pdf",
            content_bytes=b"%PDF-1.4 dummy",
        )
        result = await doc_extractor.extract(payload)

        # Scanned PDF should convert to IMAGE payload
        assert result.kind == PayloadKind.IMAGE
        assert result.content_bytes == mock_image.data
        assert result.mime_type == "image/png"
        assert result.metadata.get("source_pdf_scanned") is True
    finally:
        doc_mod.PdfReader = orig_reader
