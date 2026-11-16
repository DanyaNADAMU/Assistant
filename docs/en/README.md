# SummaryBot — User & Operator Guide

**SummaryBot** is a universal multimodal Telegram bot and CLI suite for summarization, speech-to-text (STT) transcription, and analysis across all media types.

---

## 🎯 Capabilities
* **Universal Ingestion**:
  * 🎙️ Voice messages, music, podcasts, audio tracks (`.mp3`, `.ogg`, `.wav`, `.m4a`).
  * 📹 Video and Telegram circular video notes (`.mp4`, `.mov`, `.webm`).
  * 📄 Documents & books: PDF, DOCX, TXT, Markdown.
  * 🖼️ Photos, screenshots with text (OCR), memes, stickers, animated GIFs.
  * 🔗 Web article links (automated content extraction via `trafilatura`).
  * 💬 Text messages and micro-notes.
  * 📍 Geolocation pins.
* **Resilient Routing (Primary ➔ Fallback)**:
  * Every task category defines a Primary and a Fallback model.
  * On HTTP `429 Too Many Requests`, upstream network timeouts, or 5xx outages, the bot seamlessly executes the Fallback model without failing user requests.
* **Pro Mode**:
  * Append `/pro` to any caption or message for deep, structured analytical synthesis.

---

## 💻 CLI Usage

The command-line interface allows local testing and batch processing:

```bash
# View active model matrix
uv run summary-bot models

# Process any local media file
uv run summary-bot process document.pdf

# Process web link in Pro mode and save markdown output
uv run summary-bot process "https://example.com/article" --pro -o summary.md

# Launch Telegram bot long-polling daemon
uv run summary-bot tg-serve
```

---

## 🚀 Server Deployment (Test / Staging)

SummaryBot is deployed as a rootless Podman container managed by systemd Quadlet:

1. **Service User**: `apps` on host `berg-test` (port 4021).
2. **Proxy Gateway**: Dedicated `apps-proxy-gateway` container (AmneziaWG) providing isolated European network routing.
3. **Stack Location**:
   * `/home/apps/stacks/SummaryBot/Containerfile`
   * `/home/apps/stacks/SummaryBot/SummaryBot.container`
   * `/home/apps/stacks/SummaryBot/.env` (mode `0600`)

### Service Management
```bash
systemctl --user daemon-reload
systemctl --user start SummaryBot
systemctl --user status SummaryBot
journalctl --user -u SummaryBot -f
```

---

## 🔐 Security & Release Invariants
* **Production Gate**: Deployment to production is strictly forbidden without the user explicitly sending `"sdsd"` in chat.
* **Secret Management**: Credentials (`TELEGRAM_BOT_TOKEN`, `OPENROUTER_API_KEY`) reside in Ansible Vault (`Infra` repository SSoT) and mirror to VaultWarden.
