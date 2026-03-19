# SaveBot (@My_Saves_AI_Bot)

Personal knowledge base Telegram bot.
Python 3.12 + aiogram 3.26 + aiosqlite + OpenRouter API

## Commands
- `python -m pytest tests/` — run all tests
- Deploy: SSH to server (see deploy/ and /deploy skill)
- NEVER run the bot locally — deploy to server only (causes polling conflicts)

## Architecture
- Router order in bot.py: settings → manage → menu → browse → inline → save (ORDER MATTERS!)
- State management: custom state_store (pending_states table in DB)
- AI: OpenRouter API → gemma-3-27b-it:free (with fallback chain: trinity, gemma-12b, qwen3)
- DB: aiosqlite, 9 tables, 15 migrations
- Scheduler: hourly jobs (digest, daily brief, state cleanup)

## Where to Look
| Topic | File |
|-------|------|
| Architecture decisions | @docs/decisions/ |
| Callback conventions | @.conventions/gold-standards/callback-pattern.md |
| Handler pattern | @.conventions/gold-standards/handler.py |
| Query pattern | @.conventions/gold-standards/query.py |
| State pattern | @.conventions/gold-standards/state-pattern.py |
| Anti-patterns | @.conventions/anti-patterns/callback-data.md |
| Deploy script | @deploy/setup.sh |
| Structural tests | @tests/test_architecture.py |
| Data model (all tables+fields) | @docs/data-dictionary.md |
| All query functions (index) | @savebot/db/queries.py (top docstring) |
| AI classification prompt | @savebot/services/ai_classifier.py |
| AI search prompt | @savebot/services/ai_search.py |

## Enforced Rules (tested mechanically)
- Router order enforced by `tests/test_architecture.py::TestRouterOrder`
- Callback data ≤ 64 bytes enforced by `tests/test_architecture.py::TestCallbackDataLimit`

## Callback Data Rules
- Max 64 bytes per callback_data (Telegram limit)
- Prefixes: bm: (browse menu), vi: (view item), vn: (navigate), vl: (view list), va: (view action)
- Context codes: c=category, t=tag, r=recent, p=pinned, l=readlist, f=forgotten, o=collection
- Truncate tags to 20 chars in callbacks

## Gotchas
- gemma model does NOT support system role — merge system prompt into user message
- Empty dict is falsy in Python — use `is not None` checks
- aiogram Message objects are frozen — cannot mutate fields
- Callback data > 64 bytes → TelegramBadRequest crash
- Always truncate tag text to 20 chars in callback data

## Rules
- Tests required for all query functions and services
- Deploy ONLY via SSH to server (ubuntu@151.145.86.66)
- Register new handlers in bot.py in correct router order
- New callback prefixes must follow conventions in .conventions/

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
