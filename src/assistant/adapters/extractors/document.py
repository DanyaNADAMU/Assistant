"""Document extractor adapter parsing PDF, DOCX, and text formats."""

import io
import logging
from pathlib import Path

from docx import Document
from pypdf import PdfReader

from assistant.core.models.payload import InputPayload, PayloadKind
from assistant.core.ports.extractor import MediaExtractorPort

logger = logging.getLogger(__name__)

SUPPORTED_DOC_EXTENSIONS = frozenset(
    {".pdf", ".docx", ".txt", ".md", ".rtf", ".csv", ".log", ".json", ".yaml", ".yml"}
)
IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tiff", ".tif"})


class DocumentExtractor(MediaExtractorPort):
    """Extracts raw text from PDF, DOCX, TXT, and Markdown files."""

    async def can_handle(self, payload: InputPayload) -> bool:
        """Check if payload is a document or file that can be parsed for text."""
        # Reject image documents so VisionExtractor handles them
        if payload.mime_type and payload.mime_type.startswith("image/"):
            return False

        if payload.filename:
            ext = Path(payload.filename).suffix.lower()
            if ext in IMAGE_EXTENSIONS:
                return False
            if ext in SUPPORTED_DOC_EXTENSIONS:
                return True

        return payload.kind == PayloadKind.DOCUMENT

    async def extract(self, payload: InputPayload) -> InputPayload:
        """Parse document contents and inject into payload.text."""
        extracted_text = ""
        filename = payload.filename or (payload.file_path.name if payload.file_path else "")
        ext = Path(filename).suffix.lower()

        data_bytes = payload.content_bytes
        if not data_bytes and payload.file_path and payload.file_path.exists():
            data_bytes = payload.file_path.read_bytes()

        if not data_bytes:
            return payload

        try:
            if ext == ".pdf":
                reader = PdfReader(io.BytesIO(data_bytes))
                pages = [page.extract_text() or "" for page in reader.pages]
                extracted_text = "\n\n".join(pages).strip()

                # If no text was extracted, check if this is a scanned PDF with embedded images
                if not extracted_text and reader.pages:
                    for page in reader.pages:
                        if page.images:
                            first_img = page.images[0]
                            img_ext = Path(first_img.name).suffix.lstrip(".").lower() or "jpeg"
                            payload_dict = payload.model_dump()
                            payload_dict["kind"] = PayloadKind.IMAGE
                            payload_dict["content_bytes"] = first_img.data
                            payload_dict["mime_type"] = f"image/{img_ext}"
                            payload_dict["metadata"] = {
                                **payload.metadata,
                                "source_pdf_scanned": True,
                            }
                            return InputPayload(**payload_dict)
            elif ext == ".docx":
                doc = Document(io.BytesIO(data_bytes))
                paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
                extracted_text = "\n\n".join(paragraphs).strip()
            else:
                # Plain text / Markdown / utf-8
                extracted_text = data_bytes.decode("utf-8", errors="replace").strip()
        except Exception as exc:
            logger.warning("Failed to extract document '%s': %s", filename, exc)
            return payload

        payload_dict = payload.model_dump()
        payload_dict["text"] = extracted_text
        payload_dict["kind"] = PayloadKind.TEXT
        return InputPayload(**payload_dict)
