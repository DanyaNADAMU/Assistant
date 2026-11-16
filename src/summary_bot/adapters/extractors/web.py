"""Web article content extractor using trafilatura."""

import asyncio
import logging

import trafilatura

from summary_bot.core.models.payload import InputPayload, PayloadKind
from summary_bot.core.ports.extractor import MediaExtractorPort

logger = logging.getLogger(__name__)


class WebExtractor(MediaExtractorPort):
    """Fetches web links and extracts clean article text, title, and metadata."""

    async def can_handle(self, payload: InputPayload) -> bool:
        """Check if payload is a URL or contains an HTTP link."""
        if payload.kind == PayloadKind.URL:
            return True
        if payload.url and payload.url.startswith(("http://", "https://")):
            return True
        return bool(payload.text and payload.text.strip().startswith(("http://", "https://")))

    async def extract(self, payload: InputPayload) -> InputPayload:
        """Fetch article content and populate payload.text with clean markdown/text."""
        target_url = payload.url or (payload.text.strip() if payload.text else "")
        if not target_url.startswith(("http://", "https://")):
            return payload

        logger.debug("Fetching web content from URL: %s", target_url)

        def _fetch_and_extract() -> str | None:
            downloaded = trafilatura.fetch_url(target_url)
            if not downloaded:
                return None
            return trafilatura.extract(
                downloaded,
                include_comments=False,
                include_tables=True,
                no_fallback=False,
                output_format="txt",
            )

        extracted = await asyncio.to_thread(_fetch_and_extract)

        if not extracted:
            logger.warning("Could not extract clean text from URL: %s", target_url)
            return payload

        payload_dict = payload.model_dump()
        payload_dict["url"] = target_url
        payload_dict["text"] = f"Заголовок/URL: {target_url}\n\nТекст статьи:\n{extracted}"
        payload_dict["kind"] = PayloadKind.TEXT

        return InputPayload(**payload_dict)
