# SummaryBot — Project Agent Rules

This document defines project-specific architecture, operational invariants, and deployment boundaries for SummaryBot. It applies on top of global directives (`~/Projects/Agent/AGENTS.md`).

## What This Project Is

SummaryBot is a multimodal Telegram bot and CLI suite designed to ingest all media formats: text, audio, video, circular video notes, voice messages, music, photos, stickers, GIFs, documents (PDF, DOCX, TXT), locations, and web links. It outputs structured summaries, verbatim speech-to-text (STT) transcriptions, and optional text-to-speech (TTS) synthesis.

## Non-Negotiables

- **Absolute Production Deployment Gate**: NEVER deploy to production under any circumstances without explicit user consent provided as the exact string `"sdsd"` in chat. All deployments target strictly the staging testbed (`berg-test`, port 4021).
- **Staging Isolation & User Separation**: On the `test` host (`berg-test`), SummaryBot runs strictly under user `apps`. The agent's personal `proxy-gateway` container is private to the agent and must NEVER be shared. A dedicated proxy container under user `apps` provides outbound European routing for the bot (`Network=container:apps-proxy-gateway`).
- **Core-First Architecture**: Development proceeds strictly in order: Domain Core ➔ CLI / TUI ➔ Telegram interface ➔ Web. Core never imports interfaces or adapters.
- **Resilient Model Routing**: Every task category (`AUDIO_VIDEO`, `TEXT_DOCS`, `VISION`, `MICRO`, `PRO`) defines a `Primary` and a `Fallback` model. The executor must automatically fail over on HTTP 429 (Rate Limits), HTTP 5xx, or network timeouts.
- **Zero Secret Leakage**: API tokens (`OPENROUTER_API_KEY`, `TELEGRAM_BOT_TOKEN`) must never be hardcoded or committed. Production/Staging values are stored in Ansible Vault (`Infra` repo) and mirrored to VaultWarden; runtime values are injected via `.env`.
- **Signed Commits & Immutable Timeline**: All commits and tags must be SSH-signed (`danya-git`). Conventional Commits format in English. Never force-push to `main`.
- **Bilingual Documentation**: All end-user documentation must be localized in both English (`docs/en/`) and Russian (`docs/ru/`).

## Module Boundaries

- `src/summary_bot/core/`: Pure domain logic, models (`InputPayload`, `ProcessingResult`, `TaskCategory`), port definitions (`ModelGatewayPort`, `MediaExtractorPort`), and resilient orchestration. Zero external I/O dependencies.
- `src/summary_bot/adapters/`: Concrete implementations of ports:
  - `openrouter/`: Async HTTP client for OpenRouter chat completions and multimodal inputs.
  - `extractors/`: `ffmpeg` audio demuxer, document parsers (`pypdf`, `python-docx`), web scrapers (`trafilatura`).
- `src/summary_bot/interfaces/`:
  - `cli/`: Typer + Rich command-line application (`summary-bot process ...`).
  - `telegram/`: Aiogram 3 bot dispatchers, handlers, and media downloaders.
- `src/summary_bot/config.py`: Strictly-typed Pydantic settings loading from environment variables.

Dependency direction: `interfaces` ➔ `adapters` ➔ `core`. `core` never imports `adapters` or `interfaces`.

## Model Category Matrix

| Category | Primary Model | Fallback Model |
| :--- | :--- | :--- |
| `AUDIO_VIDEO` | `xiaomi/mimo-v2.6-flash` | `qwen/qwen3.8-omni-flash` |
| `TEXT_DOCS` | `thinkingmachines/inkling-2-small:free` | `z-ai/glm-5.3-flash` |
| `VISION` | `thinkingmachines/inkling-2-small:free` | `z-ai/glm-5.3-flash` |
| `MICRO` | `z-ai/glm-5.3-flash` | `deepseek/deepseek-v4.1-flash` |
| `PRO` | `z-ai/glm-5.3` | `google/gemini-3.8-flash` |
