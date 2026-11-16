"""OpenRouter API client implementing ModelGatewayPort."""

import base64
import logging
from typing import Any

import httpx

from summary_bot.config import Settings, TaskCategory
from summary_bot.core.models.payload import InputPayload, PayloadKind
from summary_bot.core.models.result import ProcessingResult
from summary_bot.core.ports.model_gateway import ModelGatewayPort

logger = logging.getLogger(__name__)


class OpenRouterAPIError(Exception):
    """Raised when OpenRouter API returns an error response."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(f"OpenRouter API Error [{status_code}]: {message}")
        self.status_code = status_code
        self.message = message

    @property
    def is_retryable(self) -> bool:
        """Rate limit (429) or transient server errors (5xx) are retryable."""
        return self.status_code == 429 or 500 <= self.status_code < 600


class OpenRouterClient(ModelGatewayPort):
    """Asynchronous client for OpenRouter chat completions API."""

    def __init__(self, settings: Settings, http_client: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._client = http_client or httpx.AsyncClient(
            base_url=self._settings.openrouter_base_url,
            timeout=self._settings.request_timeout_seconds,
        )

    async def execute(
        self,
        payload: InputPayload,
        model: str,
        system_prompt: str,
    ) -> ProcessingResult:
        """Send inference request to OpenRouter and parse the result."""
        headers = {
            "Authorization": f"Bearer {self._settings.openrouter_api_key}",
            "HTTP-Referer": self._settings.openrouter_http_referer,
            "X-Title": self._settings.openrouter_app_title,
            "Content-Type": "application/json",
        }

        user_content = self._build_user_content(payload)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

        request_body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": 0.3,
        }

        logger.debug("Dispatching request to OpenRouter model: %s", model)

        try:
            response = await self._client.post(
                "/chat/completions",
                headers=headers,
                json=request_body,
            )
        except (httpx.TimeoutException, httpx.NetworkError) as net_err:
            logger.warning("Network/Timeout error connecting to OpenRouter: %s", net_err)
            raise OpenRouterAPIError(status_code=504, message=str(net_err)) from net_err

        if response.status_code != 200:
            error_text = response.text
            logger.warning(
                "OpenRouter returned status %d for model %s: %s",
                response.status_code,
                model,
                error_text,
            )
            raise OpenRouterAPIError(status_code=response.status_code, message=error_text)

        data = response.json()
        choices = data.get("choices", [])
        if not choices:
            raise OpenRouterAPIError(status_code=500, message="Empty choices received from OpenRouter")

        content: str = choices[0].get("message", {}).get("content", "")
        usage = data.get("usage", {})

        # Parse transcription and summary from content
        transcription, summary, takeaways = self._parse_output_sections(content)

        category_val = payload.metadata.get("category", TaskCategory.TEXT_DOCS)
        if isinstance(category_val, str):
            category_enum = TaskCategory(category_val)
        else:
            category_enum = category_val

        return ProcessingResult(
            category=category_enum,
            summary=summary,
            transcription=transcription,
            key_takeaways=takeaways,
            model_used=model,
            used_fallback=False,
            tokens_prompt=usage.get("prompt_tokens"),
            tokens_completion=usage.get("completion_tokens"),
            original_media_type=payload.kind.value,
        )

    def _build_user_content(self, payload: InputPayload) -> Any:
        """Construct multimodal message content for OpenAI/OpenRouter specification."""
        # 1. Audio / Voice / Video payload (Multimodal Omni data-URL)
        if payload.has_audio_stream:
            data_bytes = payload.content_bytes
            if not data_bytes and payload.file_path and payload.file_path.exists():
                data_bytes = payload.file_path.read_bytes()

            if data_bytes:
                mime = payload.mime_type or "audio/mp3"
                b64_data = base64.b64encode(data_bytes).decode("utf-8")
                data_url = f"data:{mime};base64,{b64_data}"
                return [
                    {
                        "type": "input_audio" if "audio" in mime else "image_url",
                        ("input_audio" if "audio" in mime else "image_url"): {
                            ("data" if "audio" in mime else "url"): (
                                b64_data if "audio" in mime else data_url
                            ),
                            **({"format": mime.split("/")[-1]} if "audio" in mime else {}),
                        },
                    },
                    {"type": "text", "text": "Пожалуйста, расшифруй аудиодорожку и сделай подробное саммари."},
                ]

        # 2. Visual payload (Photo, Sticker, GIF)
        if payload.has_visual_stream:
            data_bytes = payload.content_bytes
            if not data_bytes and payload.file_path and payload.file_path.exists():
                data_bytes = payload.file_path.read_bytes()

            if data_bytes:
                mime = payload.mime_type or "image/jpeg"
                b64_data = base64.b64encode(data_bytes).decode("utf-8")
                return [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime};base64,{b64_data}"},
                    },
                    {"type": "text", "text": payload.text or "Опиши и сделай саммари этого изображения."},
                ]

        # 3. Text or document content
        text_content = payload.text or ""
        if payload.kind == PayloadKind.LOCATION:
            lat = payload.latitude
            lon = payload.longitude
            text_content = f"Географические координаты локации: широта {lat}, долгота {lon}."
        elif payload.url:
            text_content = f"Ссылка: {payload.url}\n\nСодержимое:\n{text_content}"

        return text_content

    @staticmethod
    def _parse_output_sections(raw_text: str) -> tuple[str | None, str, list[str]]:
        """Extract [РАСШИФРОВКА] and [САММАРИ] blocks if present."""
        transcription: str | None = None
        summary: str = raw_text
        takeaways: list[str] = []

        if "[РАСШИФРОВКА]" in raw_text and "[САММАРИ]" in raw_text:
            parts = raw_text.split("[САММАРИ]")
            transcription = parts[0].replace("[РАСШИФРОВКА]", "").strip()
            summary = parts[1].strip()

        # Extract bullet points if clearly delineated
        for line in summary.splitlines():
            line_stripped = line.strip()
            if line_stripped.startswith(("• ", "- ", "* ")) and len(line_stripped) > 4:
                bullet = line_stripped.lstrip("•-* ").strip()
                if bullet and not bullet.startswith("**"):
                    takeaways.append(bullet)

        return transcription, summary, takeaways[:5]
