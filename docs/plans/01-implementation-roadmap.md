# Plan 01: Implementation Roadmap & Execution Checklist

Status: **Active**  
Trajectory: Core-First Multimodal Ingestion Pipeline

## Critical Constraints
- **Absolute Gate**: NEVER deploy to production without explicit user prompt string `"sdsd"`. Deployments target strictly the staging testbed (`berg-test`, port 4021) under user `apps`.
- **Network Isolation**: Dedicated `apps-proxy-gateway` for user `apps` on testbed. Never share agent's personal proxy container.

---

## Phase 1: Foundation & Project Skeleton
- [ ] Initialize Python 3.12+ project with Astral `uv` (`pyproject.toml`, `uv.lock`)
- [ ] Configure strict typing tools: `ruff.toml`, `mypy.ini` (strict mode)
- [ ] Create `.env.example` and Pydantic configuration module (`src/summary_bot/config.py`)
- [ ] Establish package directory structure:
  - `src/summary_bot/core/` (models, ports, services)
  - `src/summary_bot/adapters/` (openrouter, extractors)
  - `src/summary_bot/interfaces/` (cli, telegram)
  - `tests/` (unit, integration, mocks)

## Phase 2: Domain Core & Failover Orchestrator
- [ ] Implement domain models:
  - `TaskCategory` enum (`AUDIO_VIDEO`, `TEXT_DOCS`, `VISION`, `MICRO`, `PRO`)
  - `InputPayload` (raw data, file path, stream, MIME, source metadata)
  - `ProcessingResult` (transcription, summary, bullet points, metadata, failover indicator)
- [ ] Define abstract port protocols:
  - `ModelGatewayPort`
  - `MediaExtractorPort`
  - `STTPort`
- [ ] Implement `CategoryDetector` (heuristic classifier for incoming payloads)
- [ ] Implement `ResilientModelRunner` (primary ➔ fallback failover on 429/5xx/timeout)
- [ ] Write domain prompts for Russian structured summaries

## Phase 3: Adapters & Ingestion Services
- [ ] Implement `OpenRouterClient` adapter:
  - Async HTTP client with multimodal support (base64 audio/video/image)
  - Error classification (retryable vs fatal)
  - Automatic fallback execution
- [ ] Implement `AudioExtractor` adapter using `ffmpeg`:
  - Demux audio from video, circular notes (`.mp4`), voice messages (`.ogg`/`.oga`)
  - Normalize to 16kHz WAV/MP3 mono
- [ ] Implement `DocumentExtractor` adapter (`pypdf`, `python-docx`, plain text)
- [ ] Implement `WebLinkExtractor` adapter (`trafilatura` for clean article content)

## Phase 4: CLI / TUI Application & Test Suite
- [ ] Build Typer CLI (`summary-bot process <file|url|text>`) with Rich output formatting
- [ ] Add flags: `--pro`, `--category`, `--json`, `--output`
- [ ] Implement comprehensive test suite:
  - Mocked OpenRouter responses (success, 429 failover to fallback, 500 error handling)
  - Extraction tests on sample documents and audio/video files
  - Full pipeline integration tests

## Phase 5: Telegram Bot Interface (`aiogram 3`)
- [ ] Set up `aiogram 3` Dispatcher and Router structure:
  - Voice messages & audio files
  - Video & circular video notes ("кружочки")
  - Documents (PDF, DOCX, TXT)
  - Photos, stickers, GIFs
  - Text messages & URLs
  - Geolocation pins
- [ ] Implement streaming status indicators (`typing`, `record_voice`)
- [ ] Implement user commands: `/start`, `/help`, `/pro`, `/models`
- [ ] Add footer metadata badge indicating which model processed the request

## Phase 6: TTS & Polish
- [ ] Add optional Text-to-Speech (TTS) response capability
- [ ] Add user-facing bilingual documentation (`docs/en/` and `docs/ru/`)

## Phase 7: Deployment to Staging (`berg-test`)
- [ ] Write `Containerfile` and `SummaryBot.container` Quadlet
- [ ] Prepare testbed staging configuration on `berg-test` under user `apps`:
  - Set up dedicated `apps-proxy-gateway`
  - Deploy `SummaryBot` Quadlet unit
- [ ] Run end-to-end smoke test on staging
