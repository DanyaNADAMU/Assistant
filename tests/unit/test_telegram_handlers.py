"""Unit tests for Telegram interface and handler routing."""

from summary_bot.config import Settings, TaskCategory
from summary_bot.core.models.payload import InputPayload
from summary_bot.core.models.result import ProcessingResult
from summary_bot.core.services.runner import ResilientModelRunner
from summary_bot.interfaces.telegram.bot import create_dispatcher
from summary_bot.interfaces.telegram.handlers.media import _is_pro


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
    assert len(dp.sub_routers) == 2  # commands_router and media_router
