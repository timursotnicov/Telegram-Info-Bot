---
name: browse-refactor
description: |
  Analyze and safely split browse.py (1445 lines) into smaller modules by context type.
  Maps code sections, identifies shared helpers, provides a step-by-step split plan with test verification.
  Use when browse.py is too big, needs modularization, or you want to understand its structure.
  Triggers on "refactor browse", "split browse.py", "browse.py too big", "modularize handlers".
  Do NOT use for adding features (use new-handler), UX analysis (use ux-flow-checker),
  AI prompt work (use ai-classify-debug), or quick one-handler fixes.
user_invocable: true
invocation: /browse-refactor
---

# Browse Refactor

## Overview

`savebot/handlers/browse.py` is the largest handler file (~1500 lines). It handles all browsing, navigation, item viewing, sorting, and search. This skill helps you understand its structure and safely split it into smaller, focused modules.

The `browse_analyzer.py` script parses `browse.py` using the Python AST module, maps every function, groups them by purpose, and builds a dependency graph -- so you know exactly what depends on what before moving code.

## Before You Start

1. Make sure all tests pass before starting any refactor:
   ```bash
   python -m pytest tests/ -q
   ```
2. Read `tests/test_architecture.py` -- it enforces router order and callback data limits. Any split must preserve these constraints.
3. Note that `menu.py` imports `cmd_search` from browse.py. This cross-module dependency must be handled.

## Run the Analyzer

```bash
python .claude/skills/browse-refactor/scripts/browse_analyzer.py savebot/handlers/browse.py
```

This outputs:
- **Console summary** -- table of all functions with line ranges and types
- **data/browse_sections.json** -- functions grouped into proposed sections
- **data/browse_deps.json** -- dependency graph (which functions call which)

## Understanding Output

The analyzer groups functions into 5 sections:

| Section | What it contains |
|---------|-----------------|
| **core** | Constants, context maps, shared helpers (`_CTX_MAP`, `_format_item`, etc.) |
| **nav** | Single-item navigation (`vi:`, `vn:`, related items) |
| **list** | List rendering with pagination (`vl:`, `browse_cat:`, `tag_items:`) |
| **item** | Item actions (pin, delete, tags, notes, move category) |
| **commands** | Command handlers (`/browse`, `/search`, `/map`, `/sources`) |

## Target Structure

After refactoring, the browse package should look like:

```
savebot/handlers/browse/
    __init__.py      # re-exports router, cmd_search
    _core.py         # constants, helpers, shared utilities
    _nav.py          # single-item view and navigation
    _list.py         # list rendering and pagination
    _item.py         # item action handlers
    _commands.py     # slash command handlers
```

Each sub-module gets its own sub-router. The `__init__.py` assembles them into one main router that is registered in `bot.py`.

## Execution Steps

Follow this order -- run `pytest` after EACH step:

1. **Create the package directory** -- `savebot/handlers/browse/`
2. **Move `_core.py`** -- extract constants, `_CTX_MAP`, `_CTX_REV`, `_CTX_TITLES`, `SORT_LABELS`, `PAGE_SIZE`, and all private helper functions that are used by multiple sections
3. **Move `_commands.py`** -- extract command handlers (`cmd_browse`, `cmd_search`, `cmd_map`, `cmd_sources`). Update `menu.py` import to point to new location
4. **Move `_list.py`** -- extract list rendering handlers
5. **Move `_nav.py`** -- extract navigation handlers
6. **Move `_item.py`** -- extract item action handlers
7. **Create `__init__.py`** -- import sub-routers, assemble into main router, re-export `cmd_search`
8. **Delete old `browse.py`** -- replace with the package
9. **Update `bot.py`** -- import should still work (`from savebot.handlers import browse`)
10. **Final test run** -- `python -m pytest tests/ -q`

## Router Registration

Sub-routers must be included inside the browse package router:

```python
# savebot/handlers/browse/__init__.py
from aiogram import Router
from . import _commands, _nav, _list, _item

router = Router()
router.include_router(_commands.router)
router.include_router(_list.router)
router.include_router(_nav.router)
router.include_router(_item.router)

# Re-export for menu.py
from ._commands import cmd_search
```

The outer `bot.py` still does `dp.include_router(browse.router)` and `TestRouterOrder` still passes because `browse` is still a module with a `.router` attribute.

## Gotchas

- **menu.py imports `cmd_search`** from browse. After splitting, update menu.py to import from the new location: `from savebot.handlers.browse import cmd_search`
- **`_extract_list_context`** is used by multiple item action handlers. It must stay in `_core.py` and be imported by `_item.py` and `_nav.py`.
- **TestRouterOrder** in `tests/test_architecture.py` checks `dp.include_router(browse.router)` in bot.py. The regex pattern matches module names, so `browse.router` must still exist as an importable attribute.
- **Callback prefixes are split across sections** -- make sure each sub-module only registers handlers for its own prefixes. No two modules should handle the same prefix.
- **Import cycles** -- `_core.py` must NOT import from other sub-modules. All shared code goes there.
