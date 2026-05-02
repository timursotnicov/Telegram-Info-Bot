# SaveBot

Personal knowledge base Telegram bot (@My_Saves_AI_Bot). Send any text, link, or photo — SaveBot auto-categorizes it with AI and stores it for instant retrieval.

## Features

- **Auto-categorization** — AI classifies every saved item into a category and assigns tags
- **Quick capture** — prefix a message with `!` to save instantly without AI processing
- **Search** — full-text search across all saved items
- **/ask AI answers** — ask questions about your saved knowledge, get AI-synthesized answers
- **Collections** — group related items into named collections
- **Daily Brief** — configurable daily summary of recent saves
- **Related Items** — discover connections between saved items
- **Tags** — browse and filter by auto-assigned or manually edited tags
- **Pinned Items** — pin important items for quick access
- **Read List** — mark items to read later
- **Inline mode** — search your saves from any Telegram chat

## Tech Stack

- **Python 3.12**
- **aiogram 3.26** — async Telegram bot framework
- **aiosqlite** — async SQLite database
- **APScheduler** — background jobs (digest, daily brief)
- **OpenRouter API** — AI classification via gemma-3-27b-it:free with fallback chain

## Setup

```bash
git clone https://github.com/timursotnicov/Telegram-Info-Bot.git
cd Telegram-Info-Bot

# Create dev env file
cp .env.example .env.dev
# Fill in: BOT_TOKEN, OPENROUTER_API_KEY

# Install dependencies
pip install -r requirements.txt

# Run
python -m savebot.bot
```

### Required Environment Variables

| Variable | Description |
|---|---|
| `BOT_TOKEN` | Telegram bot token from @BotFather |
| `OPENROUTER_API_KEY` | API key from openrouter.ai |

## Bot Commands

| Command | Description |
|---|---|
| `/browse` | Browse items by category, tag, or collection |
| `/search <query>` | Full-text search |
| `/recent` | View recently saved items |
| `/help` | Show help message |
| `/settings` | Preferences (daily brief, digest, etc.) |
| `/export` | Export all saved items |
| `/stats` | Usage statistics |

## Persistent Keyboard

Five quick-access buttons always visible at the bottom:

`Browse` | `Search` | `Pinned` | `Recent` | `Settings`

## Project Structure

```
savebot/
  bot.py             — Entry point, router registration
  config.py          — Environment config
  middleware.py       — DB injection middleware
  scheduler.py        — Background jobs
  handlers/           — Telegram message/callback handlers
  services/           — AI, search, digest, OCR, link preview
  db/                 — Schema, queries, migrations, state store
tests/               — pytest test suite (134 tests)
deploy/              — Server setup script
```

## Deploy

```bash
cp .env.prod.example .env.prod
# Fill in production secrets, then on the server:
./deploy.sh
```

Deploys to an Oracle Cloud VM in Docker Compose production mode, enables SSH-only
firewall rules, fail2ban, and SQLite backups before container restart.

### Restore from Telegram Export

```bash
python scripts/import_telegram_export.py "C:\Users\Timmy\Downloads\Telegram Desktop\ChatExport_2026-05-02" --seed-db savebot_backup_2026-03-22.db --db savebot.db
```

## Testing

```bash
python -m pytest tests/
```

## License

Private project.
