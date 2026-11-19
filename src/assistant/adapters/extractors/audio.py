"""Audio extractor adapter using ffmpeg to demux, trim silence, and normalize loudness."""

import asyncio
import contextlib
import logging
import tempfile
from pathlib import Path

from assistant.core.models.payload import InputPayload, PayloadKind
from assistant.core.ports.extractor import MediaExtractorPort

logger = logging.getLogger(__name__)

# Standard silence removal and EBU R128 loudness normalization filter chain
VOICE_OPTIMIZATION_FILTER = (
    "silenceremove=start_periods=1:start_duration=0.3:start_threshold=-45dB:"
    "stop_periods=1:stop_duration=0.5:stop_threshold=-45dB,"
    "loudnorm=I=-16:TP=-1.5:LRA=11"
)


async def probe_audio_duration(file_path: Path) -> float | None:
    """Extract audio/video stream duration in seconds via ffprobe."""
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(file_path),
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        if proc.returncode == 0:
            val = stdout.decode().strip()
            return float(val) if val else None
    except Exception as exc:
        logger.debug("ffprobe failed for %s: %s", file_path, exc)
    return None


class AudioExtractor(MediaExtractorPort):
    """Demuxes video, video notes and converts non-standard audio to 16kHz mono MP3.

    Applies intelligent silence removal and broadcast-standard loudness normalization.
    """

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

        # Probe original duration
        original_duration = await probe_audio_duration(source_path)

        metadata = dict(payload.metadata)
        if original_duration is not None:
            metadata["original_duration"] = original_duration

        # 1. Attempt optimized conversion with silence removal and loudness normalization
        cmd_optimized = [
            "ffmpeg",
            "-y",
            "-i",
            str(source_path),
            "-vn",  # Disable video
            "-af",
            VOICE_OPTIMIZATION_FILTER,
            "-ac",
            "1",  # Mono
            "-ar",
            "16000",  # 16kHz sample rate
            "-b:a",
            "64k",  # 64kbps bitrate
            "-f",
            "mp3",
            str(out_path),
        ]

        logger.debug("Executing optimized ffmpeg: %s", " ".join(cmd_optimized))
        proc = await asyncio.create_subprocess_exec(
            *cmd_optimized,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()

        use_fallback = False
        if proc.returncode != 0:
            logger.debug(
                "Optimized ffmpeg returned %d, falling back to basic transcode", proc.returncode
            )
            use_fallback = True
        elif not out_path.exists() or out_path.stat().st_size < 512:
            # File is completely silent (silenceremove stripped everything)
            logger.info("Audio stream contains no audible speech (silence-only detected)")
            metadata["is_silent"] = True
            use_fallback = True

        if use_fallback:
            # Basic fallback without filters
            cmd_fallback = [
                "ffmpeg",
                "-y",
                "-i",
                str(source_path),
                "-vn",
                "-ac",
                "1",
                "-ar",
                "16000",
                "-b:a",
                "64k",
                "-f",
                "mp3",
                str(out_path),
            ]
            proc_fb = await asyncio.create_subprocess_exec(
                *cmd_fallback,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, fb_stderr = await proc_fb.communicate()
            if proc_fb.returncode != 0:
                logger.warning(
                    "Fallback ffmpeg failed with code %d: %s",
                    proc_fb.returncode,
                    fb_stderr.decode("utf-8", errors="replace"),
                )
                if source_temp_created:
                    with contextlib.suppress(OSError):
                        source_path.unlink(missing_ok=True)
                out_path.unlink(missing_ok=True)
                return payload
        else:
            # Successfully trimmed & normalized
            trimmed_duration = await probe_audio_duration(out_path)
            if trimmed_duration is not None:
                metadata["duration_seconds"] = trimmed_duration
                if original_duration is not None:
                    saved = round(max(0.0, original_duration - trimmed_duration), 2)
                    metadata["silence_saved_seconds"] = saved
            metadata["loudnorm_applied"] = True
            metadata["silence_trimmed"] = True

        if source_temp_created:
            with contextlib.suppress(OSError):
                source_path.unlink(missing_ok=True)

        if not out_path.exists() or out_path.stat().st_size == 0:
            out_path.unlink(missing_ok=True)
            return payload

        # Read back normalized audio bytes
        extracted_bytes = out_path.read_bytes()
        out_path.unlink(missing_ok=True)

        if "duration_seconds" not in metadata and original_duration is not None:
            metadata["duration_seconds"] = original_duration

        # Return updated payload marked as audio/mp3 with enriched metadata
        payload_dict = payload.model_dump()
        payload_dict["content_bytes"] = extracted_bytes
        payload_dict["mime_type"] = "audio/mp3"
        payload_dict["file_path"] = None
        payload_dict["metadata"] = metadata

        return InputPayload(**payload_dict)
