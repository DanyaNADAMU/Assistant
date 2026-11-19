"""Unit tests for Telegram interface and handler routing."""

from assistant.config import Settings, TaskCategory
from assistant.core.models.payload import InputPayload
from assistant.core.models.result import ProcessingResult
from assistant.core.services.runner import ResilientModelRunner
from assistant.interfaces.telegram.bot import create_dispatcher
from assistant.interfaces.telegram.handlers.media import _is_pro


class DummyGateway:
    async def execute(
        self,
        payload: InputPayload,
        model: str,
        system_prompt: str,
    ) -> ProcessingResult:
        _ = payload
        _ = system_prompt
        return ProcessingResult(
            category=TaskCategory.TEXT_DOCS,
            summary="Dummy summary",
            model_used=model,
        )


def test_is_pro_detection() -> None:
    assert _is_pro(caption="Please analyze /pro", text=None) is True
    assert _is_pro(caption=None, text="Check this out --pro") is True
    assert _is_pro(caption="Normal caption", text=None) is False
    assert _is_pro(caption=None, text="Normal text") is False


def test_create_dispatcher_routes() -> None:
    settings = Settings()
    runner = ResilientModelRunner(gateway=DummyGateway(), settings=settings)
    dp = create_dispatcher(runner)

    assert dp["runner"] == runner
    assert len(dp.sub_routers) == 4  # commands_router, callbacks_router, inline_router, and media_router
