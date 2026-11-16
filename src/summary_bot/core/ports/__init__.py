"""Core port protocols exports."""

from summary_bot.core.ports.extractor import MediaExtractorPort
from summary_bot.core.ports.model_gateway import ModelGatewayPort

__all__ = ["MediaExtractorPort", "ModelGatewayPort"]
