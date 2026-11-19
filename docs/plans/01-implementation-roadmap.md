# Plan 01: Implementation Roadmap & Execution Checklist

Status: **Active**  
Trajectory: Core-First Multimodal Ingestion Pipeline

## Critical Constraints
- **Release Contours**: Feature/fix branches deploy to staging (Actions); production deploys run only on signed `v*` tags via GitHub Actions.
- **Network Isolation**: Dedicated `apps-proxy-gateway` for user `apps` on testbed. Never share agent's personal proxy container.

---

## Phase 1: Foundation & Project Skeleton
- [x] Initialize Python 3.12+ project with Astral `uv` (`pyproject.toml`, `uv.lock`)
- [x] Configure strict typing tools: `ruff.toml`, `mypy.ini` (strict mode)
- [x] Create `.env.example` and Pydantic configuration module (`src/assistant/config.py`)
- [x] Establish package directory structure:
  - `src/assistant/core/` (models, ports, services)
  - `src/assistant/adapters/` (openrouter, extractors)
  - `src/assistant/interfaces/` (cli, telegram)
  - `tests/` (unit, integration, mocks)

## Phase 2: Domain Core & Failover Orchestrator
- [x] Implement domain models:
  - `TaskCategory` enum (`AUDIO_VIDEO`, `TEXT_DOCS`, `VISION`, `MICRO`, `PRO`)
  - `InputPayload` (raw data, file path, stream, MIME, source metadata)
  - `ProcessingResult` (transcription, summary, bullet points, metadata, failover indicator)
- [x] Define abstract port protocols:
  - `ModelGatewayPort`
  - `MediaExtractorPort`
- [x] Implement `CategoryDetector` (heuristic classifier for incoming payloads)
- [x] Implement `ResilientModelRunner` (primary ➔ fallback failover on 429/5xx/timeout)
- [x] Write domain prompts for Russian structured summaries

## Phase 3: Adapters & Ingestion Services
- [x] Implement `OpenRouterClient` adapter:
  - Async HTTP client with multimodal support (base64 audio/video/image)
  - Error classification (retryable vs fatal)
  - Automatic fallback execution
- [x] Implement `AudioExtractor` adapter using `ffmpeg`:
  - Demux audio from video, circular notes (`.mp4`), voice messages (`.ogg`/`.oga`)
  - Normalize to 16kHz WAV/MP3 mono
- [x] Implement `DocumentExtractor` adapter (`pypdf`, `python-docx`, plain text)
- [x] Implement `WebLinkExtractor` adapter (`trafilatura` for clean article content)

## Phase 4: CLI / TUI Application & Test Suite
- [x] Build Typer CLI (`assistant process <file|url|text>`) with Rich output formatting
- [x] Add flags: `--pro`, `--category`, `--json`, `--output`
- [x] Implement comprehensive test suite:
  - Mocked OpenRouter responses (success, 429 failover to fallback, 500 error handling)
  - Extraction tests on sample documents and audio/video files
  - Full pipeline integration tests

## Phase 5: Telegram Bot Interface (`aiogram 3`)
- [x] Set up `aiogram 3` Dispatcher and Router structure:
  - Voice messages & audio files
  - Video & circular video notes ("кружочки")
  - Documents (PDF, DOCX, TXT)
  - Photos, stickers, GIFs
  - Text messages & URLs
  - Geolocation pins
- [x] Implement streaming status indicators (`typing`, `record_voice`)
- [x] Implement user commands: `/start`, `/help`, `/pro`, `/models`
- [x] Add footer metadata badge indicating which model processed the request

## Phase 6: Documentation, Containerization & Packaging
- [x] Write `Containerfile` (Debian Bookworm Slim + ffmpeg + uv + non-root user `apps`)
- [x] Write `Assistant.container` Quadlet unit file for systemd
- [x] Add user-facing bilingual documentation (`docs/en/` and `docs/ru/`)

## Phase 7: Deployment to Staging (`berg-test`)
- [x] Prepare testbed staging configuration on `berg-test` under user `apps`:
  - [x] Set up dedicated `apps-proxy-gateway` (AmneziaWG via Frankfurt node)
  - [x] Deploy `Assistant` Quadlet unit in user session
- [x] Run end-to-end smoke test on staging (Telegram polling, OpenRouter connectivity verified)

---

## Phase 8: Hardening, Enhancements & Production Readiness
- [ ] **Access Control & Anti-Abuse**:
  - Whitelist mode (`ALLOWED_TELEGRAM_USERS`) or per-user daily quota
  - Graceful rejection messages for unauthorized users
- [ ] **Interactive Follow-Up Q&A (Contextual Dialog)**:
  - Ability to reply to a summary message with follow-up questions
  - In-memory or Redis/SQLite context window tracking
- [ ] **Content Caching & Dedup**:
  - Hash-based deduplication for files and URLs (skip redundant LLM API calls)
  - SQLite/PostgreSQL storage for usage analytics and token spend
- [ ] **Text-to-Speech (TTS) Summaries**:
  - Optional audio summary playback via Edge-TTS / ElevenLabs / OpenRouter
- [ ] **CI/CD & Git Maintenance**:
  - Pull Request review on Forgejo (`feat/foundation-and-core` -> `main`)
  - Forgejo Actions test runner pipeline
  - Bitcoin OTS synchronization
- [x] **Production Rollout**:
  - Signed release tag `v*` triggers `release.yml` GitHub Actions deploy to production (Ice)
