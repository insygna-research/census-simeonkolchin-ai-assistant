# Getting Started

This guide walks you through running AI Assistant locally or with Docker.

## Prerequisites

- Python 3.11+ (for local runs) or Docker + Docker Compose
- At least one LLM provider key (DeepSeek, OpenAI, or GigaChat)
- Optional: Telegram, iCloud, GitLab, YouGile, Outline credentials

## 1. Clone and configure

```bash
git clone https://github.com/simeonkolchin/ai-assistant.git
cd ai-assistant
cp .env.example .env
```

Edit `.env` and set at least one LLM key, for example:

```dotenv
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=sk-your-key
```

Every integration follows the **"empty key = disabled"** rule — leave anything
you don't need blank.

## 2. Run with Docker Compose (recommended)

Docker Compose also starts a bundled [SearXNG](https://github.com/searxng/searxng)
backend for web search.

```bash
docker compose up --build
```

Open the web UI at <http://localhost:8082>.

## 3. Run locally with Python

```bash
pip install -r requirements.txt
playwright install --with-deps chromium   # required for the browser tool
python main.py
```

The server listens on <http://localhost:8080> by default (`HOST` / `PORT` in
`.env`).

## 4. First login

The web UI is protected by OIDC / JWT. For local experimentation you can set
`AUTH_DISABLED=true` in `.env`. In production, configure the `OIDC_*` variables.

## 5. Connecting Telegram

Set `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, and `TELEGRAM_PHONE`. On first use
Telethon creates a session file under `TELEGRAM_SESSION_PATH` (default
`./data/sessions`). This file is gitignored — never commit it. Restrict which
chats the agent may act on with `TELEGRAM_ALLOWED_CHATS`.

## Next steps

- [Architecture](architecture.md) — how the pieces fit together
- [Configuration reference](../.env.example) — every setting explained
