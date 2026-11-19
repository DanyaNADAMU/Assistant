"""Request intent model distinguishing analysis from media generation."""

from enum import StrEnum


class RequestIntent(StrEnum):
    """Top-level intent of an incoming request.

    This is the first branching decision in the pipeline, resolved before
    content extraction. ``ANALYZE`` keeps the existing summarization/STT/OCR
    path; ``GENERATE_IMAGE`` and ``GENERATE_VIDEO`` route to the media
    generation backends (currently Venice.AI).
    """

    ANALYZE = "analyze"
    GENERATE_IMAGE = "generate_image"
    GENERATE_VIDEO = "generate_video"
