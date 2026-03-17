# Telegram-Info-Bot

## Project Overview

Personal knowledge management bot for Telegram. Saves messages, classifies them with AI,
and provides intelligent search across saved content.

## Tech Stack

- **Python 3.10+** with async/await
- **aiogram v3** — Telegram Bot Framework (routers, filters, middleware)
- **aiosqlite** — async SQLite with FTS5 for full-text search
- **OpenRouter API** — LLM calls (classification, search, OCR)
- **APScheduler** — periodic tasks (digests, cleanup)

## Project Structure

```
savebot/
├── bot.py              # Entry point, dispatcher setup
├── config.py           # Environment-based configuration
├── middleware.py        # Error handling middleware
├── scheduler.py         # APScheduler jobs
├── db/
│   ├── models.py       # SQLite schema & migrations
│   ├── queries.py      # All database operations
│   └── state_store.py  # Temporary state for multi-step flows
├── services/
│   ├── ai_classifier.py  # Content categorization via LLM
│   ├── ai_search.py      # Query parsing & answer synthesis
│   ├── ocr.py             # Vision-based text extraction
│   ├── link_preview.py    # URL metadata fetching
│   ├── digest.py          # Weekly/daily digest generation
│   └── connections.py     # Related items discovery
└── handlers/
    ├── save.py          # Message capture & auto-save
    ├── browse.py        # Category/tag/context browsing
    ├── manage.py        # /start, /help, /stats, /export
    ├── menu.py          # Persistent keyboard & state
    ├── settings.py      # User preferences
    └── inline.py        # Inline queries
```

## Key Conventions

- All I/O is async (use `await`, `async def`)
- Database operations go through `savebot/db/queries.py` — never write raw SQL in handlers
- LLM calls use OpenRouter with retry logic and model fallbacks (see `ai_classifier.py`)
- Handlers are organized as aiogram Routers, registered in `bot.py`
- User-facing text supports Russian and English
- Before modifying AI prompts, read existing prompts in services/ to maintain consistency

## Context Hub

This project uses Context Hub for providing up-to-date documentation to AI agents during development.
See `docs/context-hub-dev-guide.md` for details.

When working on this codebase, refer to project documentation in `docs/` for:
- API integration patterns (OpenRouter, Telegram)
- Database schema and FTS5 query syntax
- AI prompt engineering guidelines

# gstack

- For all web browsing, use the /browse skill from gstack. Never use mcp__claude-in-chrome__* tools.
- Available gstack skills:
  - /plan-ceo-review — CEO/founder-mode plan review
  - /plan-eng-review — Eng manager-mode plan review
  - /review — Pre-landing PR review
  - /ship — Ship workflow (merge, test, review, bump, push, PR)
  - /browse — Fast headless browser for QA testing and site dogfooding
  - /qa — Systematic QA testing of web applications
  - /setup-browser-cookies — Import cookies from real browser into headless session
  - /retro — Weekly engineering retrospective
