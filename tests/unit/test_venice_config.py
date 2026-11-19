"""Tests for Venice.AI media generation configuration."""

from assistant.config import Settings


def test_venice_defaults() -> None:
    settings = Settings()
    assert settings.venice_base_url == "https://api.venice.ai/api/v1"
    assert settings.gen_image_model == "venice-sd35"
    assert settings.gen_image_model_photoreal == "flux-3-image"
    assert settings.gen_image_model_anime == "wai-Illustrious"
    assert settings.gen_video_text_model == "wan-2-7-text-to-video"
    assert settings.gen_video_image_model == "wan-2-7-image-to-video"
    assert settings.gen_video_duration == "5s"
    assert settings.gen_video_resolution == "720p"
    assert settings.gen_video_aspect_ratio == "16:9"


def test_venice_override_via_env() -> None:
    settings = Settings(
        VENICE_API_KEY="sk-venice-test",
        GEN_IMAGE_MODEL="flux-3-image",
        GEN_VIDEO_DURATION="10s",
        GEN_VIDEO_RESOLUTION="1080p",
    )
    assert settings.venice_api_key == "sk-venice-test"
    assert settings.gen_image_model == "flux-3-image"
    assert settings.gen_video_duration == "10s"
    assert settings.gen_video_resolution == "1080p"


def test_venice_api_key_is_sanitized() -> None:
    settings = Settings(VENICE_API_KEY=' "sk-venice" raw ')
    assert settings.venice_api_key == 'sk-venice" raw'
