"""Unit tests for ResilientModelRunner failover mechanism."""

import pytest

from assistant.adapters.openrouter.client import OpenRouterAPIError
from assistant.config import Settings, TaskCategory
from assistant.core.models.payload import InputPayload, PayloadKind
from assistant.core.models.result import ProcessingResult
from assistant.core.services.runner import ResilientModelRunner


class MockGateway:
    """Mock gateway that simulates primary failure and fallback success."""

    def __init__(self, fail_models: set[str]) -> None:
        self.fail_models = fail_models
        self.call_history: list[str] = []

    async def execute(
        self,
        payload: InputPayload,
        model: str,
        system_prompt: str,
    ) -> ProcessingResult:
        _ = payload
        _ = system_prompt
        self.call_history.append(model)
        if model in self.fail_models:
            raise OpenRouterAPIError(status_code=429, message="Rate limit exceeded on free tier")

        return ProcessingResult(
            category=TaskCategory.TEXT_DOCS,
            summary="Mocked structured summary",
            model_used=model,
            used_fallback=False,
        )


@pytest.mark.asyncio
async def test_successful_primary_execution() -> None:
    settings = Settings()
    primary_model, _ = settings.get_models_for_category(TaskCategory.TEXT_DOCS)

    gateway = MockGateway(fail_models=set())
    runner = ResilientModelRunner(gateway=gateway, settings=settings)

    payload = InputPayload(kind=PayloadKind.TEXT, text="A" * 200)
    result = await runner.run(payload)

    assert result.used_fallback is False
    assert result.model_used == primary_model
    assert gateway.call_history == [primary_model]


@pytest.mark.asyncio
async def test_failover_to_fallback_on_429() -> None:
    settings = Settings()
    primary_model, fallback_model = settings.get_models_for_category(TaskCategory.TEXT_DOCS)

    # Primary model will fail with 429
    gateway = MockGateway(fail_models={primary_model})
    runner = ResilientModelRunner(gateway=gateway, settings=settings)

    payload = InputPayload(kind=PayloadKind.TEXT, text="A" * 200)
    result = await runner.run(payload)

    assert result.used_fallback is True
    assert result.model_used == fallback_model
    assert gateway.call_history == [primary_model, fallback_model]
    assert "[fallback]" in result.format_telegram_message()


@pytest.mark.asyncio
async def test_both_primary_and_fallback_fail() -> None:
    settings = Settings()
    primary_model, fallback_model = settings.get_models_for_category(TaskCategory.TEXT_DOCS)

    # Both fail
    gateway = MockGateway(fail_models={primary_model, fallback_model})
    runner = ResilientModelRunner(gateway=gateway, settings=settings)

    payload = InputPayload(kind=PayloadKind.TEXT, text="A" * 200)

    with pytest.raises(OpenRouterAPIError) as exc_info:
        await runner.run(payload)

    assert exc_info.value.status_code == 429
    assert gateway.call_history == [primary_model, fallback_model]
