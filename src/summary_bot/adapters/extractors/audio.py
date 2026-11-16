"""Audio extractor adapter using ffmpeg to demux and normalize audio streams."""

import asyncio
import contextlib
import logging
import tempfile
from pathlib import Path

from summary_bot.core.models.payload import InputPayload, PayloadKind
from summary_bot.core.ports.extractor import MediaExtractorPort

logger = logging.getLogger(__name__)


class AudioExtractor(MediaExtractorPort):
    """Demuxes video, video notes and converts non-standard audio to 16kHz mono MP3."""

    async def can_handle(self, payload: InputPayload) -> bool:
        """Check if payload is video or needs audio stream extraction."""
        return payload.kind in (
            PayloadKind.VIDEO,
            PayloadKind.VIDEO_NOTE,
            PayloadKind.AUDIO,
            PayloadKind.VOICE,
        )

    async def extract(self, payload: InputPayload) -> InputPayload:
        """Extract audio stream from video/audio container into a normalized MP3 file."""
        source_path = payload.file_path
        source_temp_created = False

        # If payload only has bytes, write to a temporary file for ffmpeg
        if not source_path or not source_path.exists():
            if not payload.content_bytes:
                return payload
            with tempfile.NamedTemporaryFile(delete=False, suffix=".bin") as temp_in:
                temp_in.write(payload.content_bytes)
                source_path = Path(temp_in.name)
            source_temp_created = True

        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as out_temp:
            out_path = Path(out_temp.name)

        # Run ffmpeg to convert to 16kHz mono MP3 (optimal for OpenRouter audio)
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(source_path),
            "-vn",              # Disable video recording
            "-ac",
            "1",                # Mono
            "-ar",
            "16000",            # 16kHz sample rate
            "-b:a",
            "64k",              # 64kbps bitrate
            "-f",
            "mp3",
            str(out_path),
        ]

        logger.debug("Executing ffmpeg: %s", " ".join(cmd))
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await process.communicate()

        if source_temp_created:
            with contextlib.suppress(OSError):
                source_path.unlink(missing_ok=True)

        if process.returncode != 0:
            logger.warning(
                "ffmpeg failed with exit code %d: %s",
                process.returncode,
                stderr.decode("utf-8", errors="replace"),
            )
            out_path.unlink(missing_ok=True)
            return payload

        # Read back normalized audio bytes
        extracted_bytes = out_path.read_bytes()
        out_path.unlink(missing_ok=True)

        # Return updated payload marked as audio/mp3
        payload_dict = payload.model_dump()
        payload_dict["content_bytes"] = extracted_bytes
        payload_dict["mime_type"] = "audio/mp3"
        payload_dict["file_path"] = None

        return InputPayload(**payload_dict)
