# Architecture

## Stack

- **Python 3.12** — runtime
- **aiogram 3.26** — async Telegram bot framework
- **aiosqlite** — async SQLite wrapper
- **APScheduler** — background job scheduler
- **OpenRouter API** — AI classification via gemma-3-27b-it:free with fallback chain

## File Structure

```
savebot/
  bot.py              — Entry point, router registration, bot commands
  config.py           — Environment config (dataclass)
  middleware.py        — DB injection middleware
  scheduler.py         — Hourly jobs: digest, daily brief, state cleanup
  handlers/
    settings.py       — /settings + preference toggles
    manage.py         — /start, /help, /delete, /categories, /export, /stats
    menu.py           — Persistent keyboard button handlers (BEFORE save.py)
    browse.py         — /browse, /search, /ask, /collections, /tags, item view
    inline.py         — Inline query handler
    save.py           — Catch-all: auto-save + quick capture (! prefix)
  services/
    ai_classifier.py  — AI categorization (OpenRouter + fallbacks)
    ai_search.py      — Query parsing + answer synthesis
    connections.py     — Related items (tags -> category -> FTS)
    digest.py          — Weekly digest + Daily Brief
    link_preview.py    — URL extraction + HTML meta parsing
    ocr.py             — Image OCR (Gemini Flash vision)
  db/
    models.py         — Schema (9 tables)
    queries.py        — All DB functions (~70 functions)
    state_store.py    — Custom state management
    migrations.py     — 15 migrations
```

## Router Order (critical!)

```
settings -> manage -> menu -> browse -> inline -> save
```

`save.py` is a catch-all handler — it must be registered **last**. Any handler registered after it will never receive messages, because `save.py` matches everything.

## DB Schema (9 tables)

| Table | Purpose |
|---|---|
| `items` | All saved items (text, links, photos) |
| `categories` | User-defined and AI-assigned categories |
| `item_tags` | Many-to-many tags on items |
| `items_fts` | Full-text search index (SQLite FTS5) |
| `pending_states` | Custom state management (replaces aiogram FSM) |
| `user_preferences` | Per-user settings (daily brief, digest, etc.) |
| `digest_log` | Tracks when digests were last sent |
| `collections` | Named groups of items |
| `collection_items` | Many-to-many: items in collections |

## Callback Data Convention

Telegram limits callback data to **64 bytes**. All callbacks use short prefixes:

**Item view:** `vi:` (view), `vn:` (note), `vl:` (link), `va:` (action), `vd:` (delete), `vy:` (confirm), `vx:` (cancel)

**Browse:** `bc:` (category), `bm:` (menu/hub)

**Settings:** `settings_*`

**Save:** `save_*`

**Context codes** (appended to callbacks to preserve navigation state):
- `c` = category, `t` = tag, `r` = recent, `p` = pinned
- `l` = read list, `f` = forgotten, `o` = collection

Tags in callbacks are truncated to 20 characters to stay within the 64-byte limit.

## AI Pipeline

```
User saves item
  -> OpenRouter API call (gemma-3-27b-it:free)
  -> On failure: fallback chain (trinity -> gemma-12b -> qwen3)
  -> Returns: category + tags + summary
```

Key details:
- **System prompt merged into user message** — gemma models do not support a separate system role
- **Prompts optimized for small free models** with few-shot examples for consistent output
- **Fallback chain** handles rate limits (429) and model errors (400)

## State Management

Custom `state_store` module (not aiogram FSM). States are stored in the `pending_states` SQLite table and cleaned up hourly by the scheduler.

Active states:
- `search_prompt` — waiting for search query
- `rename_cat` — waiting for new category name
- `awaiting` — generic waiting state
- `new_browse_cat` — creating a category
- `edit_tags` — editing item tags
- `edit_note` — editing item note
- `new_collection` — creating a collection

## Deploy

- **Oracle Cloud VM** (Ubuntu/ARM)
- **systemd service** for process management
- **SQLite** database with daily backup cron
- Deploy script: `deploy/setup.sh`
