"""Unit tests for interactive post-summary actions and callback workflows."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import Message

from assistant.config import Settings, TaskCategory
from assistant.core.models.payload import InputPayload
from assistant.core.models.result import ProcessingResult
from assistant.core.services.context_store import SummaryContext, SummaryContextStore
from assistant.core.services.prompts import get_refinement_prompt
from assistant.core.services.runner import ResilientModelRunner
from assistant.interfaces.telegram.handlers.callbacks import handle_summary_action
from assistant.interfaces.telegram.keyboards import get_summary_keyboard


class MockGateway:
    """Mock gateway recording calls and returning predictable refinement results."""

    def __init__(self, should_fail_primary: bool = False) -> None:
        self.should_fail_primary = should_fail_primary
        self.call_history: list[dict[str, str]] = []

    async def execute(
        self,
        payload: InputPayload,
        model: str,
        system_prompt: str,
    ) -> ProcessingResult:
        _ = payload
        self.call_history.append({"model": model, "system_prompt": system_prompt})
        if self.should_fail_primary and "primary" in model.lower():
            raise RuntimeError("Simulated primary failure")

        return ProcessingResult(
            category=TaskCategory.TEXT_DOCS,
            summary=f"Refined output via {model}",
            model_used=model,
        )


@pytest.mark.asyncio
async def test_context_store_lifecycle() -> None:
    store = SummaryContextStore(max_size=2, ttl_seconds=1.0)
    ctx1 = SummaryContext.create(
        original_text="Text 1",
        source_content="Content 1",
        summary="Summary 1",
    )
    ctx2 = SummaryContext.create(
        original_text="Text 2",
        source_content="Content 2",
        summary="Summary 2",
    )
    ctx3 = SummaryContext.create(
        original_text="Text 3",
        source_content="Content 3",
        summary="Summary 3",
    )

    await store.put(ctx1)
    await store.put(ctx2)
    assert await store.get(ctx1.cid) is not None
    assert await store.get(ctx2.cid) is not None

    # Adding ctx3 must evict ctx1 due to max_size=2
    await store.put(ctx3)
    assert await store.get(ctx1.cid) is None
    assert await store.get(ctx2.cid) is not None
    assert await store.get(ctx3.cid) is not None


def test_summary_keyboards() -> None:
    # Original view without transcription
    kb_orig = get_summary_keyboard(cid="abc12345", active_view="orig", has_transcription=False)
    callback_data = [btn.callback_data for row in kb_orig.inline_keyboard for btn in row]
    assert "act:abc12345:tldr" in callback_data
    assert "act:abc12345:actions" in callback_data
    assert "act:abc12345:deep" in callback_data
    assert "act:abc12345:trans" in callback_data
    assert "act:abc12345:orig" not in callback_data

    # Refined view (actions) with transcription
    kb_act = get_summary_keyboard(cid="abc12345", active_view="actions", has_transcription=True)
    callback_data_act = [btn.callback_data for row in kb_act.inline_keyboard for btn in row]
    assert "act:abc12345:orig" in callback_data_act
    assert "act:abc12345:actions" not in callback_data_act
    assert "act:abc12345:stt" in callback_data_act


@pytest.mark.asyncio
async def test_runner_refine_with_failover() -> None:
    gateway = MockGateway(should_fail_primary=True)
    settings = Settings(
        model_text_primary="primary/test-model",
        model_text_fallback="fallback/test-model",
    )
    runner = ResilientModelRunner(gateway=gateway, settings=settings)

    result = await runner.refine(
        source_content="Test document content",
        action="actions",
        category=TaskCategory.TEXT_DOCS,
    )

    assert "fallback/test-model" in result
    assert len(gateway.call_history) == 2
    assert gateway.call_history[0]["model"] == "primary/test-model"
    assert gateway.call_history[1]["model"] == "fallback/test-model"


def test_refinement_prompts() -> None:
    for action in ["actions", "tldr", "deep", "trans"]:
        prompt = get_refinement_prompt(action)
        assert len(prompt) > 50


@pytest.mark.asyncio
async def test_callback_handler_workflow() -> None:
    from assistant.core.services.context_store import context_store

    ctx = SummaryContext.create(
        original_text="Original Message Formatted",
        source_content="Raw context data",
        summary="Base summary",
        transcription="Hello voice world",
        model_used="test-llm",
    )
    await context_store.put(ctx)

    gateway = MockGateway(should_fail_primary=False)
    settings = Settings()
    runner = ResilientModelRunner(gateway=gateway, settings=settings)

    # 1. Test action 'actions'
    mock_msg = AsyncMock(spec=Message)
    mock_cb = MagicMock()
    mock_cb.data = f"act:{ctx.cid}:actions"
    mock_cb.message = mock_msg
    mock_cb.answer = AsyncMock()

    await handle_summary_action(mock_cb, runner=runner)

    assert mock_msg.edit_text.called
    edit_args = mock_msg.edit_text.call_args[0][0]
    assert "Задачи и действия" in edit_args

    # 2. Test cached retrieval (second click should not re-query gateway)
    history_len = len(gateway.call_history)
    await handle_summary_action(mock_cb, runner=runner)
    assert len(gateway.call_history) == history_len

    # 3. Test back to original view ('orig')
    mock_cb.data = f"act:{ctx.cid}:orig"
    await handle_summary_action(mock_cb, runner=runner)
    edit_orig_args = mock_msg.edit_text.call_args[0][0]
    assert edit_orig_args == "Original Message Formatted"

    # 4. Test missing/expired CID
    mock_cb.data = "act:nonexist:actions"
    await handle_summary_action(mock_cb, runner=runner)
    mock_cb.answer.assert_called_with(
        "⚠️ Контекст сообщения устарел. Отправьте материал повторно для анализа.",
        show_alert=True,
    )
