"""Tests for the Venice.AI media generation client (httpx mock transport)."""

import asyncio
import base64
import json

import httpx
import pytest

from assistant.adapters.venice import VeniceClient
from assistant.config import Settings
from assistant.core.models.generated import GeneratedMediaError

IMG_PATH = "/api/v1/image/generate"
QUEUE_PATH = "/api/v1/video/queue"
RETRIEVE_PATH = "/api/v1/video/retrieve"
COMPLETE_PATH = "/api/v1/video/complete"


def _png_bytes() -> bytes:
    # Minimal valid PNG signature; only MIME-sniffed, not decoded.
    return b"\x89PNG\r\n\x1a\n" + b"binary-content"


def _client_with(handler):
    """Build a VeniceClient over a mock httpx transport."""
    transport = httpx.MockTransport(handler)
    http = httpx.AsyncClient(transport=transport)
    settings = Settings(VENICE_API_KEY="sk-venice")
    client = VeniceClient(settings=settings, http_client=http)
    return client


async def _close(client: VeniceClient) -> None:
    await client._client.aclose()


def test_generate_image_raw_binary() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == IMG_PATH
        payload = json.loads(request.content)
        assert payload["model"] == "venice-sd35"
        assert payload["return_binary"] is True
        assert payload["prompt"] == "a cat"
        return httpx.Response(200, content=_png_bytes(), headers={"content-type": "image/png"})

    async def run() -> None:
        client = _client_with(handler)
        media = await client.generate_image("a cat", model="venice-sd35")
        assert media.kind.value == "image"
        assert media.mime_type == "image/png"
        assert media.content_bytes == _png_bytes()
        assert media.model_used == "venice-sd35"
        await _close(client)

    asyncio.run(run())


def test_generate_image_base64_json() -> None:
    encoded = base64.b64encode(_png_bytes()).decode()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == IMG_PATH
        return httpx.Response(
            200,
            json={"data": [{"b64_json": encoded}]},
            headers={"content-type": "application/json"},
        )

    async def run() -> None:
        client = _client_with(handler)
        media = await client.generate_image("a cat", model="venice-sd35", format="png")
        assert media.content_bytes == _png_bytes()
        assert media.mime_type == "image/png"
        await _close(client)

    asyncio.run(run())


def test_generate_image_raises_on_non_200() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="unauthorized")

    async def run() -> None:
        client = _client_with(handler)
        with pytest.raises(GeneratedMediaError) as exc_info:
            await client.generate_image("a cat", model="venice-sd35")
        assert exc_info.value.status_code == 401
        assert exc_info.value.is_retryable is False
        await _close(client)

    asyncio.run(run())


def test_generate_video_queues_and_polls() -> None:
    queue_id = "q-123"
    mp4_bytes = b"\x00\x00\x00\x18ftypmp42video-bytes"

    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        payload = json.loads(request.content)
        if request.url.path == QUEUE_PATH:
            assert payload["model"] == "wan-2-7-text-to-video"
            assert payload["duration"] == "5s"
            return httpx.Response(200, json={"queue_id": queue_id})
        if request.url.path == RETRIEVE_PATH:
            retrieve_calls = calls.count(RETRIEVE_PATH)
            if retrieve_calls == 1:
                return httpx.Response(200, json={"status": "PROCESSING"})
            # Complete inline as raw mp4 bytes.
            return httpx.Response(200, content=mp4_bytes, headers={"content-type": "video/mp4"})
        raise AssertionError(f"unexpected path {request.url.path}")

    async def run() -> None:
        client = _client_with(handler)
        client._settings.gen_video_poll_interval = 0.01
        media = await client.generate_video(
            "a cat running",
            model="wan-2-7-text-to-video",
            duration="5s",
            resolution="720p",
        )
        assert media.kind.value == "video"
        assert media.mime_type == "video/mp4"
        assert media.resolution == "720p"
        assert calls == [QUEUE_PATH, RETRIEVE_PATH, RETRIEVE_PATH]
        await _close(client)

    asyncio.run(run())


def test_generate_video_completes_with_download_url() -> None:
    mp4_bytes = b"download-url-video-bytes"

    def handler(request: httpx.Request) -> httpx.Response:
        # Route by method + absolute URL.
        if request.method == "POST" and request.url.path == QUEUE_PATH:
            return httpx.Response(200, json={"queue_id": "q-url"})
        if request.method == "POST" and request.url.path == RETRIEVE_PATH:
            return httpx.Response(
                200, json={"status": "COMPLETED", "download_url": "https://cdn.example/out.mp4"}
            )
        if request.method == "GET" and str(request.url) == "https://cdn.example/out.mp4":
            return httpx.Response(200, content=mp4_bytes, headers={"content-type": "video/mp4"})
        raise AssertionError(f"unexpected request {request.method} {request.url}")

    async def run() -> None:
        client = _client_with(handler)
        client._settings.gen_video_poll_interval = 0.01
        media = await client.generate_video("a cat", model="wan-2-7-text-to-video", duration="5s")
        assert media.content_bytes == mp4_bytes
        await _close(client)

    asyncio.run(run())


def test_generate_video_times_out() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == QUEUE_PATH:
            return httpx.Response(200, json={"queue_id": "q-timeout"})
        return httpx.Response(200, json={"status": "PROCESSING"})

    async def run() -> None:
        client = _client_with(handler)
        client._settings.gen_video_poll_interval = 0.01
        client._settings.gen_video_timeout = 0.03
        with pytest.raises(GeneratedMediaError) as exc_info:
            await client.generate_video("x", model="wan-2-7-text-to-video")
        assert exc_info.value.status_code == 504
        await _close(client)

    asyncio.run(run())
