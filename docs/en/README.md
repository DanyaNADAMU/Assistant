# Assistant — User & Operator Guide

**Assistant** is a universal multimodal Telegram bot and CLI suite for summarization, speech-to-text (STT) transcription, and analysis across all media types.

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
uv run assistant models

# Process any local media file
uv run assistant process document.pdf

# Process web link in Pro mode and save markdown output
uv run assistant process "https://example.com/article" --pro -o summary.md

# Launch Telegram bot long-polling daemon
uv run assistant tg-serve
```

---

## 🚀 Server Deployment

Assistant is deployed as a rootless Podman container managed by systemd Quadlet.
GitHub Actions builds the image to GHCR and rolls it out over SSH through a
digest-pinned forced-command wrapper.

* **Test sandbox**: user `apps` on **Actions** (LXC container on Ice).
* **Production**: user `apps` on **Ice**.
* **Stack layout** (Infra-provisioned):
  * quadlet `/etc/containers/systemd/users/<uid>/assistant.container`
  * env `~/stacks/Assistant/.env` (mode `0600`)
  * data `~/stacks/Assistant/data`

### Service Management
```bash
systemctl --user daemon-reload
systemctl --user start Assistant
systemctl --user status Assistant
journalctl --user -u Assistant -f
```

---

## 🔐 Security & Release Invariants
* **Release Gate**: Production deploys run only on signed `v*` tags via GitHub Actions (`release.yml`), which verifies the `CHANGELOG.md` release section.
* **Secret Management**: Credentials (`TELEGRAM_BOT_TOKEN`, `OPENROUTER_API_KEY`) reside in Ansible Vault (`Infra` repository SSoT) and mirror to VaultWarden.
