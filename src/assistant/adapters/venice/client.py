"""Venice.AI media generation client (uncensored image/video backend).

Implements :class:`MediaGenerationPort`. Venice exposes:

* synchronous image generation at ``/image/generate`` (base64 JSON or raw
  binary via ``return_binary``);
* asynchronous video generation at ``/video/queue`` (returns a ``queue_id``),
  polled at ``/video/retrieve`` until an ``video/mp4`` body or download URL is
  returned, then cleaned up at ``/video/complete``.

All network calls go through ``httpx`` so tests can inject a fake transport.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from typing import TYPE_CHECKING, Any

import httpx

from assistant.core.models.generated import (
    GeneratedMedia,
    GeneratedMediaError,
    GeneratedMediaKind,
)
from assistant.core.ports.media_generation import MediaGenerationPort

if TYPE_CHECKING:
    from assistant.config import Settings

logger = logging.getLogger(__name__)

__all__ = ["GeneratedMediaError", "VeniceClient"]

_IMAGE_ENDPOINT = "/image/generate"
_VIDEO_QUOTE_ENDPOINT = "/video/quote"
_VIDEO_QUEUE_ENDPOINT = "/video/queue"
_VIDEO_RETRIEVE_ENDPOINT = "/video/retrieve"
_VIDEO_COMPLETE_ENDPOINT = "/video/complete"


class VeniceClient(MediaGenerationPort):
    """Asynchronous client for Venice.AI image and video generation."""

    def __init__(self, settings: Settings, http_client: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        endpoint = self._settings.venice_base_url.rstrip("/")
        self._endpoint = endpoint
        # Build absolute request URLs from the configured base so the client
        # works transparently with httpx.MockTransport in tests (mock
        # transports require absolute URLs and cannot resolve relative ones).
        self._client = http_client or httpx.AsyncClient(
            timeout=httpx.Timeout(self._settings.request_timeout_seconds, read=120.0),
        )

    def _url(self, path: str) -> str:
        """Resolve a (possibly relative) API path against the configured base."""
        if path.startswith(("http://", "https://")):
            return path
        return f"{self._endpoint}{path}"

    # ---------------------------------------------------------------- image
    async def generate_image(
        self,
        prompt: str,
        *,
        model: str,
        negative_prompt: str | None = None,
        width: int | None = None,
        height: int | None = None,
        format: str | None = None,
    ) -> GeneratedMedia:
        """Generate an image from a text prompt via the synchronous endpoint."""
        payload: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "return_binary": True,
        }
        if negative_prompt:
            payload["negative_prompt"] = negative_prompt
        if width is not None:
            payload["width"] = width
        if height is not None:
            payload["height"] = height
        if format:
            payload["format"] = format

        data = await self._post(_IMAGE_ENDPOINT, payload)
        # When return_binary=true Venice streams raw bytes; guard against a
        # JSON wrapper anyway.
        if isinstance(data, bytes):
            content_bytes = data
            mime = _infer_mime(content_bytes, fallback=f"image/{format or 'png'}")
        else:
            content_bytes = _extract_b64(data)
            mime = f"image/{format or 'png'}"

        logger.info("Generated image with %s (%d bytes)", model, len(content_bytes))
        return GeneratedMedia(
            kind=GeneratedMediaKind.IMAGE,
            content_bytes=content_bytes,
            mime_type=mime,
            model_used=model,
            prompt=prompt,
            width=width,
            height=height,
        )

    # ---------------------------------------------------------------- video
    async def generate_video(
        self,
        prompt: str,
        *,
        model: str,
        from_image_bytes: bytes | None = None,
        from_image_mime: str | None = None,
        duration: str | None = None,
        resolution: str | None = None,
        aspect_ratio: str | None = None,
        negative_prompt: str | None = None,
    ) -> GeneratedMedia:
        """Generate a video (text-to-video or image-to-video) via async queue."""
        from_image_b64: str | None = None
        if from_image_bytes is not None:
            mime = from_image_mime or "image/png"
            from_image_b64 = f"data:{mime};base64,{base64.b64encode(from_image_bytes).decode()}"

        payload: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
        }
        if negative_prompt:
            payload["negative_prompt"] = negative_prompt
        if duration:
            payload["duration"] = duration
        if resolution:
            payload["resolution"] = resolution
        if aspect_ratio:
            payload["aspect_ratio"] = aspect_ratio
        if from_image_b64:
            payload["image_url"] = from_image_b64

        queue_data = await self._post(_VIDEO_QUEUE_ENDPOINT, payload)
        queue_id = queue_data.get("queue_id")
        if not queue_id:
            raise GeneratedMediaError(
                status_code=500, message="Video queue did not return queue_id"
            )

        download_url = queue_data.get("download_url")
        content_bytes, elapsed = await self._poll_video(model, queue_id, download_url)

        logger.info("Generated video with %s (%d bytes, %.0fs)", model, len(content_bytes), elapsed)
        return GeneratedMedia(
            kind=GeneratedMediaKind.VIDEO,
            content_bytes=content_bytes,
            mime_type="video/mp4",
            model_used=model,
            prompt=prompt,
            duration_sec=duration,
            resolution=resolution,
        )

    async def _poll_video(
        self, model: str, queue_id: str, download_url: str | None
    ) -> tuple[bytes, float]:
        """Poll /video/retrieve until the MP4 is ready (or timeout)."""
        interval = self._settings.gen_video_poll_interval
        timeout = self._settings.gen_video_timeout
        elapsed = 0.0
        while elapsed < timeout:
            data = await self._post(
                _VIDEO_RETRIEVE_ENDPOINT, {"model": model, "queue_id": queue_id}
            )
            # Components send raw video bytes (Content-Type video/mp4) or a
            # JSON dict with a completion status / download_url.
            if isinstance(data, bytes):
                # Strip any text wrapper and trim trailing newline if present.
                if data.startswith(b"{"):
                    decoded = self._decode_json(data, default_url=download_url)
                    url = decoded.get("download_url")
                    if url:
                        return await self._download(url), elapsed
                    continue
                return data, elapsed

            status = data.get("status", "").upper()
            if status == "COMPLETED":
                url = data.get("download_url") or download_url
                if url:
                    return await self._download(url), elapsed
                raise GeneratedMediaError(
                    status_code=500, message="Video COMPLETED but no download_url provided"
                )
            if status == "FAILED":
                raise GeneratedMediaError(
                    status_code=500, message=f"Video generation FAILED: {data.get('error', '')}"
                )

            await asyncio.sleep(interval)
            elapsed += interval

        raise GeneratedMediaError(status_code=504, message="Video generation timed out")

    async def _download(self, url: str) -> bytes:
        resp = await self._client.get(self._url(url))
        resp.raise_for_status()
        return resp.content

    # ---------------------------------------------------------------- helpers
    async def _post(self, endpoint: str, payload: dict[str, Any]) -> Any:
        """POST JSON to Venice and return parsed JSON or raw binary content."""
        headers = {
            "Authorization": f"Bearer {self._settings.venice_api_key}",
            "Content-Type": "application/json",
        }
        try:
            response = await self._client.post(self._url(endpoint), headers=headers, json=payload)
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise GeneratedMediaError(status_code=504, message=str(exc)) from exc

        if response.status_code != 200:
            raise GeneratedMediaError(status_code=response.status_code, message=response.text)

        ctype = response.headers.get("content-type", "")
        if ctype.startswith("video/mp4") or ctype.startswith("image/"):
            return response.content
        try:
            return response.json()
        except Exception:
            # Some endpoints return raw bytes without a media content-type.
            return response.content

    def _decode_json(self, raw: bytes, *, default_url: str | None) -> dict[str, Any]:
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {"download_url": default_url} if default_url else {}


def _extract_b64(data: dict[str, Any]) -> bytes:
    """Extract and base64-decode image bytes from a Venice JSON response."""
    # Possible shapes: {"data":[{"b64_json": "..."}]} or {"b64_json": "..."}
    raw = data.get("b64_json")
    if raw is None:
        d = data.get("data")
        if isinstance(d, list) and d:
            raw = d[0].get("b64_json")
    if isinstance(raw, str):
        return base64.b64decode(raw)
    # Fall back to a raw base64-embedded URL if present.
    url = data.get("url")
    if isinstance(url, str) and url.startswith("data:"):
        return base64.b64decode(url.split(",", 1)[1])
    raise GeneratedMediaError(status_code=500, message="Image payload did not contain base64 JSON")


def _infer_mime(data: bytes, *, fallback: str) -> str:
    """Best-effort MIME sniff for raw image bytes."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"
    return f"image/{fallback}"
