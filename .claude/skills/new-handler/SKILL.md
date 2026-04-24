---
name: new-handler
description: |
  Scaffold a new aiogram handler for SaveBot. Creates handler file from gold standard template,
  registers router in bot.py, sets up callback data following conventions.
  Use when adding a new feature that needs its own handler module.
  Do NOT use for adding logic to existing handlers.
---

# New Handler Scaffold

## Arguments
$ARGUMENTS should be the handler name (e.g., "todo", "reminders", "export_v2")

## Steps

### 1. Read the gold standard
Read `.conventions/gold-standards/handler.py` to understand the handler pattern.

### 2. Read callback conventions
Read `.conventions/gold-standards/callback-pattern.md` for callback data rules.

### 3. Create handler file
Create `savebot/handlers/$ARGUMENTS.py` following the gold standard:
- Import Router from aiogram
- Create router = Router(name="$ARGUMENTS")
- Define callback data prefix (2-3 chars, check existing prefixes don't conflict)
- Add command handler and/or callback handlers
- Follow existing patterns from browse.py, manage.py

### 4. Register router in bot.py
Read `savebot/bot.py` and add the new router import.
IMPORTANT: Router order matters! Place the new router in the correct position:
- Before `save.py` (catch-all) — always
- After `menu.py` — usually
- Consider if it needs to be before/after browse.py

### 5. Create test file
Create `tests/test_$ARGUMENTS.py` with at least:
- Basic import test
- One test per command handler
- One test per callback handler

### 6. Verify
```bash
python -m pytest tests/test_$ARGUMENTS.py -v
```

## Callback Data Rules (from conventions)
- Max 64 bytes total
- Use short prefix (2-3 chars + colon)
- Context codes: c=category, t=tag, r=recent, p=pinned, l=readlist, f=forgotten, o=collection
- Truncate any user text to 20 chars
- Test that all callback data fits in 64 bytes
