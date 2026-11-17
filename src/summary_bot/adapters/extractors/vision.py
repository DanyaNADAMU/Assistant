"""Vision and image extractor adapter using Pillow."""

import io
import logging
from pathlib import Path

from PIL import Image

from summary_bot.core.models.payload import InputPayload, PayloadKind
from summary_bot.core.ports.extractor import MediaExtractorPort

logger = logging.getLogger(__name__)

SUPPORTED_IMAGE_EXTENSIONS = frozenset(
    {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tiff", ".tif"}
)
MAX_IMAGE_DIMENSION = 2048


class VisionExtractor(MediaExtractorPort):
    """Inspects, normalizes, and optimizes visual payloads for Vision LLMs."""

    async def can_handle(self, payload: InputPayload) -> bool:
        """Check if payload is a photo, visual sticker, or image document."""
        if payload.has_visual_stream:
            return True

        if payload.mime_type and payload.mime_type.startswith("image/"):
            return True

        if payload.filename:
            ext = Path(payload.filename).suffix.lower()
            return ext in SUPPORTED_IMAGE_EXTENSIONS

        return False

    async def extract(self, payload: InputPayload) -> InputPayload:
        """Inspect, resize oversized images, convert formats, and optimize bytes."""
        data_bytes = payload.content_bytes
        if not data_bytes and payload.file_path and payload.file_path.exists():
            data_bytes = payload.file_path.read_bytes()

        if not data_bytes:
            return payload

        try:
            with Image.open(io.BytesIO(data_bytes)) as img:
                orig_format = img.format or "JPEG"
                orig_w, orig_h = img.size
                active_img: Image.Image = img

                # Resize if exceeding maximum dimension while preserving aspect ratio
                if orig_w > MAX_IMAGE_DIMENSION or orig_h > MAX_IMAGE_DIMENSION:
                    scale = min(MAX_IMAGE_DIMENSION / orig_w, MAX_IMAGE_DIMENSION / orig_h)
                    new_w = int(orig_w * scale)
                    new_h = int(orig_h * scale)
                    active_img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
                    logger.info(
                        "Resized oversized image from %dx%d to %dx%d",
                        orig_w,
                        orig_h,
                        new_w,
                        new_h,
                    )
                else:
                    new_w, new_h = orig_w, orig_h

                output_buffer = io.BytesIO()
                # If image has alpha channel or palette, convert to RGB for JPEG, or preserve PNG
                if active_img.mode in ("RGBA", "LA", "P"):
                    if orig_format.upper() in ("PNG", "WEBP"):
                        active_img.save(output_buffer, format="PNG", optimize=True)
                        mime_type = "image/png"
                    else:
                        rgb_img = active_img.convert("RGB")
                        rgb_img.save(output_buffer, format="JPEG", quality=85, optimize=True)
                        mime_type = "image/jpeg"
                elif active_img.mode != "RGB":
                    rgb_img = active_img.convert("RGB")
                    rgb_img.save(output_buffer, format="JPEG", quality=85, optimize=True)
                    mime_type = "image/jpeg"
                else:
                    active_img.save(output_buffer, format="JPEG", quality=85, optimize=True)
                    mime_type = "image/jpeg"

                optimized_bytes = output_buffer.getvalue()

            payload_dict = payload.model_dump()
            payload_dict["kind"] = PayloadKind.IMAGE
            payload_dict["content_bytes"] = optimized_bytes
            payload_dict["mime_type"] = mime_type
            payload_dict["metadata"] = {
                **payload.metadata,
                "image_width": new_w,
                "image_height": new_h,
                "original_dimensions": f"{orig_w}x{orig_h}",
                "optimized_size_bytes": len(optimized_bytes),
            }
            return InputPayload(**payload_dict)

        except Exception as exc:
            logger.warning("Failed to optimize visual payload: %s", exc)
            # Retain original payload if optimization fails
            return payload
