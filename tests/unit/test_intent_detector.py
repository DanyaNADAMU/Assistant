"""Tests for request intent detection."""

from assistant.core.models.intent import RequestIntent
from assistant.core.services.intent_detector import IntentDetector


def test_none_command_is_analyze() -> None:
    assert IntentDetector.detect(None) == RequestIntent.ANALYZE


def test_empty_command_is_analyze() -> None:
    assert IntentDetector.detect("") == RequestIntent.ANALYZE


def test_image_command_maps_to_generate_image() -> None:
    assert IntentDetector.detect("/image") == RequestIntent.GENERATE_IMAGE


def test_image_with_trailing_parts() -> None:
    assert IntentDetector.detect("/image a cat") == RequestIntent.GENERATE_IMAGE


def test_image_bare_slug() -> None:
    assert IntentDetector.detect("image") == RequestIntent.GENERATE_IMAGE


def test_video_command_maps_to_generate_video() -> None:
    assert IntentDetector.detect("/video") == RequestIntent.GENERATE_VIDEO


def test_video_bare_slug() -> None:
    assert IntentDetector.detect("video") == RequestIntent.GENERATE_VIDEO


def test_unknown_command_is_analyze() -> None:
    assert IntentDetector.detect("/unknown") == RequestIntent.ANALYZE


def test_leading_whitespace_is_normalized() -> None:
    assert IntentDetector.detect("  /IMAGE  ") == RequestIntent.GENERATE_IMAGE


def test_is_generation_flag() -> None:
    assert IntentDetector.is_generation(RequestIntent.GENERATE_IMAGE) is True
    assert IntentDetector.is_generation(RequestIntent.GENERATE_VIDEO) is True
    assert IntentDetector.is_generation(RequestIntent.ANALYZE) is False
