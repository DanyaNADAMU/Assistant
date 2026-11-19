"""Port definition for Model Gateway."""

from typing import Protocol, runtime_checkable

from assistant.core.models.payload import InputPayload
from assistant.core.models.result import ProcessingResult


@runtime_checkable
class ModelGatewayPort(Protocol):
    """Protocol for sending multimodal/text queries to LLM backends."""

    async def execute(
        self,
        payload: InputPayload,
        model: str,
        system_prompt: str,
    ) -> ProcessingResult:
        """Execute inference on the specified model."""
        ...
