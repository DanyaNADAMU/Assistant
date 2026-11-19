# Assistant

Universal multimodal Telegram bot and CLI for summarization, speech-to-text (STT) transcription, and analysis across all media types.

## Features

- **Any media in**: voice, music, podcasts, video and circular video notes, documents (PDF/DOCX/TXT/Markdown), images and screenshots (OCR), web links, text, and geolocation.
- **Resilient model routing**: every task category defines a Primary → Fallback model pair with automatic failover on `429`, `5xx`, or timeouts.
- **Pro mode** (`/pro`) for deep, structured analysis.
- Interactive inline mode, multi-URL batch processing, document export, persistent response cache, per-user preferences, and a personal bookmarks/knowledge archive.

## CLI

```bash
uv run assistant models                          # view the model matrix
uv run assistant process document.pdf            # summarise a local file
uv run assistant process "https://example.com" --pro -o summary.md
uv run assistant tg-serve                        # run the Telegram bot
```

## Documentation

- User & operator guide: [`docs/en/`](docs/en/) and [`docs/ru/`](docs/ru/).
- Architecture, ADRs and plans: [`docs/`](docs/).

## CI/CD & Deployment

GitHub Actions builds and publishes the container image to GHCR
(`ghcr.io/danyanadamu/assistant`). Feature/fix branches deploy to the **Actions**
test sandbox; signed `v*` tags deploy to **Ice** (production).

## Security

See [`SECURITY.md`](SECURITY.md). Secrets live in Ansible Vault (`Infra`) and are
injected at runtime via `.env`; nothing secret is committed to this repository.
