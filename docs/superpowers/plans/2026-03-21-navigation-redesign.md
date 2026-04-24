# Navigation Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Simplify bot navigation — fewer clicks, readable item lists, cleaner structure.

**Architecture:** Remove category sub-menu (direct to list), switch item lists from buttons to formatted text with number buttons, remove unused screens (tags/collections/map/forgotten/global channels), add Settings to keyboard, add AI-powered category cleanup in settings.

**Tech Stack:** Python 3.12, aiogram 3.26, aiosqlite, OpenRouter API

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `savebot/handlers/manage.py:25-32` | Modify | MAIN_KEYBOARD: 4 new buttons |
| `savebot/handlers/menu.py:20-24` | Modify | BUTTON_TEXTS + handler routing |
| `savebot/handlers/browse_core.py` | Modify | `_categories_markup`, `_back_button_for_ctx`, `_clickable_list_buttons`, `_format_item_list`, `_show_list`, `_show_categories_msg`; remove `_more_markup`, `_show_collections` |
| `savebot/handlers/browse.py` | Modify | Remove handlers (hub, tags, map, forgotten, collections, global sources, sub-menu); update `cmd_search`; fix `cs:` back button |
| `savebot/handlers/settings.py` | Modify | Add "🧹 Умная уборка" button |
| `savebot/services/ai_cleanup.py` | Create | AI category consolidation service |
| `savebot/handlers/cleanup.py` | Create | Handlers for cleanup flow |
| `savebot/bot.py` | Modify | Register cleanup router (after settings, before manage) |
| `tests/test_architecture.py` | Modify | Update callback patterns, remove obsolete ones |
| `tests/test_browse.py` | Modify | Update for new list format, removed features |
| `tests/test_cleanup.py` | Create | Tests for AI cleanup service |

---

### Task 1: Update persistent keyboard and button routing

**Files:**
- Modify: `savebot/handlers/manage.py:25-32`
- Modify: `savebot/handlers/menu.py:20-24, 153-179`
- Test: `tests/test_architecture.py`

- [ ] **Step 1: Update MAIN_KEYBOARD in manage.py**

```python
MAIN_KEYBOARD = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📂 Все записи"), KeyboardButton(text="🔍 Поиск")],
        [KeyboardButton(text="🕐 Недавние"), KeyboardButton(text="⚙️ Настройки")],
    ],
    resize_keyboard=True,
    is_persistent=True,
)
```

- [ ] **Step 2: Update BUTTON_TEXTS in menu.py**

```python
BUTTON_TEXTS = {
    "📂 Все записи", "🔍 Поиск", "🕐 Недавние", "⚙️ Настройки",
    # Backward compat: old buttons cached on some clients
    "📂 Категории", "📂 Browse", "🔍 Search", "📌 Pinned",
    "🕐 Recent", "⚙️ Settings", "📌 Закрепленные",
}
```

- [ ] **Step 3: Update handle_keyboard_button routing in menu.py**

Replace the button routing block (lines ~162-179):

```python
    if text in ("📂 Все записи", "📂 Категории", "📂 Browse"):
        from savebot.handlers.browse import cmd_browse
        await cmd_browse(message, db=db)

    elif text in ("🔍 Поиск", "🔍 Search"):
        user_id = message.from_user.id
        await set_state(db, f"search_prompt_{user_id}", user_id, "search_prompt", {})
        await message.reply("🔍 Введите поисковый запрос:")

    elif text in ("📌 Закрепленные", "📌 Pinned"):
        from savebot.handlers.browse import cmd_pinned
        await cmd_pinned(message, db=db)

    elif text in ("🕐 Недавние", "🕐 Recent"):
        from savebot.handlers.browse import cmd_recent
        await cmd_recent(message, db=db)

    elif text in ("⚙️ Настройки", "⚙️ Settings"):
        from savebot.handlers.settings import cmd_settings
        await cmd_settings(message, db=db)

    else:
        from aiogram.dispatcher.event.bases import SkipHandler
        raise SkipHandler
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_architecture.py -v`
Expected: PASS (keyboard changes don't break router order)

- [ ] **Step 5: Commit**

```bash
git add savebot/handlers/manage.py savebot/handlers/menu.py
git commit -m "feat: update keyboard — Все записи, Поиск, Недавние, Настройки"
```

---

### Task 2: Direct category navigation (remove sub-menu)

**Files:**
- Modify: `savebot/handlers/browse_core.py:238-251` (`_categories_markup`)
- Modify: `savebot/handlers/browse_core.py:214-225` (`_back_button_for_ctx`)
- Modify: `savebot/handlers/browse_core.py:269-286` (`_show_categories_msg`)
- Modify: `savebot/handlers/browse.py:119-150` (`cs:` back button)

- [ ] **Step 1: Change _categories_markup — direct to browse_cat**

Replace `_categories_markup` in browse_core.py:

```python
def _categories_markup(categories: list[dict]) -> InlineKeyboardMarkup:
    """Build category list buttons — tap goes directly to item list."""
    buttons = []
    for cat in categories:
        emoji = cat.get("emoji", "\U0001f4c1")
        buttons.append([InlineKeyboardButton(
            text=f"{emoji} {cat['name']} ({cat['item_count']})",
            callback_data=f"browse_cat:{cat['id']}:0",
        )])
    return InlineKeyboardMarkup(inline_keyboard=buttons)
```

- [ ] **Step 2: Update _back_button_for_ctx — all say "Все записи"**

Replace `_back_button_for_ctx` in browse_core.py:

```python
def _back_button_for_ctx(ctx_short: str, ctx_id: str | int = "0") -> InlineKeyboardButton:
    """Return the appropriate back button for a given context."""
    if ctx_short == "c":
        return InlineKeyboardButton(text="\U0001f519 Все записи", callback_data="bm:cats")
    elif ctx_short == "s":
        return InlineKeyboardButton(text="\U0001f519 Все записи", callback_data="bm:cats")
    else:
        return InlineKeyboardButton(text="\U0001f519 Все записи", callback_data="bm:cats")
```

- [ ] **Step 3: Update _show_categories_msg — remove "Ещё" fallback**

Replace `_show_categories_msg` in browse_core.py:

```python
async def _show_categories_msg(message: types.Message, db=None):
    """Show category list for commands/keyboard (sends new message)."""
    user_id = message.from_user.id
    categories = await queries.get_all_categories(db, user_id)
    if not categories:
        await message.reply(
            "📂 <b>Записей пока нет.</b> Отправьте мне текст, ссылку или файл!",
            parse_mode="HTML",
        )
        return
    await message.reply(
        "📂 <b>Все записи:</b>",
        reply_markup=_categories_markup(categories),
        parse_mode="HTML",
    )
```

- [ ] **Step 4: Add "📨 Каналы" footer to category list in _show_list**

In `_show_list` (browse_core.py), after the back button line (`buttons.append([_back_button_for_ctx(...)])`), add channels button for category context:

```python
    # Footer buttons
    footer = [_back_button_for_ctx(ctx_short, ctx_id)]
    if context_type == "category":
        footer.insert(0, InlineKeyboardButton(
            text="📨 Каналы",
            callback_data=f"cs:{ctx_id}:0",
        ))
    buttons.append(footer)
```

Replace the existing `buttons.append([_back_button_for_ctx(ctx_short, ctx_id)])` line.

- [ ] **Step 5: Fix cs: handler back button**

In browse.py `on_category_sources`, change back button from `cm:{cat_id}` to `browse_cat:{cat_id}:0`:

```python
    buttons.append([InlineKeyboardButton(text="🔙 К списку", callback_data=f"browse_cat:{cat_id}:0")])
```

- [ ] **Step 6: Update on_hub_cats callback to also use new markup**

In browse.py `on_hub_cats`, update the empty-state fallback (remove "Ещё" button):

```python
    if not categories:
        await callback.message.edit_text(
            "📂 <b>Записей пока нет.</b>",
            parse_mode="HTML",
        )
        await callback.answer()
        return
```

- [ ] **Step 7: Run tests**

Run: `python -m pytest tests/ -v`
Expected: Some tests may fail (test_browse references removed features). Note failures for Task 7.

- [ ] **Step 8: Commit**

```bash
git add savebot/handlers/browse_core.py savebot/handlers/browse.py
git commit -m "feat: category tap goes directly to item list, remove sub-menu"
```

---

### Task 3: Text-based item lists

**Files:**
- Modify: `savebot/handlers/browse_core.py:88-211` (formatters + list builders)

- [ ] **Step 1: Add _format_item_list_text helper**

Add new function in browse_core.py after `_format_item_short`:

```python
def _format_item_list_entry(item: dict, num: int) -> str:
    """Format a single item for text-based list view."""
    # Title (full, not truncated)
    if item.get("ai_summary"):
        title = html.escape(item["ai_summary"])
    elif item.get("content_text"):
        title = html.escape(item["content_text"][:120])
    else:
        title = "(без текста)"

    line = f"<b>{num}.</b> {title}"

    # Meta line: category + source + date + tags
    meta_parts = []
    if item.get("category_emoji") and item.get("category_name"):
        meta_parts.append(f"{item['category_emoji']} {item['category_name']}")
    if item.get("source"):
        meta_parts.append(f"📨 {html.escape(item['source'])}")
    if item.get("created_at"):
        date_str = str(item["created_at"])[:10]
        meta_parts.append(date_str)

    tags = item.get("tags", [])
    if tags:
        meta_parts.append(" ".join(f"#{t}" for t in tags[:3]))

    if meta_parts:
        line += f"\n   {' · '.join(meta_parts)}"

    return line
```

- [ ] **Step 2: Rewrite _clickable_list_buttons for text+number layout**

Replace `_clickable_list_buttons` in browse_core.py:

```python
def _clickable_list_buttons(
    items: list[dict],
    ctx_short: str,
    ctx_id: str | int,
    offset: int,
    total: int,
    deleting_item_id: int | None = None,
    sort_by: str = "d",
) -> tuple[str, list[list[InlineKeyboardButton]]]:
    """Build text + number buttons for a list view.

    Returns (text_block, buttons) where text_block contains formatted items
    and buttons are number keys + pagination.
    """
    text_lines = []
    number_buttons = []
    buttons = []

    for i, item in enumerate(items):
        num = item.get("display_num", i + 1 + offset)
        display_i = i + 1

        if deleting_item_id and item["id"] == deleting_item_id:
            text_lines.append(f"<b>{display_i}.</b> <s>{_format_item_short(item)}</s>  🗑 Удалить?")
            buttons.append([
                InlineKeyboardButton(text=f"✅ Да", callback_data=f"vy:{ctx_short}:{ctx_id}:{item['id']}:{offset}"),
                InlineKeyboardButton(text=f"❌ Нет", callback_data=f"vx:{ctx_short}:{ctx_id}:{offset}"),
            ])
        else:
            text_lines.append(_format_item_list_entry(item, display_i))
            number_buttons.append(InlineKeyboardButton(
                text=str(display_i),
                callback_data=f"vi:{ctx_short}:{ctx_id}:{item['id']}",
            ))

    # Number buttons row (e.g. [1] [2] [3] [4] [5])
    if number_buttons:
        buttons.insert(0, number_buttons)

    # Pagination row
    page = offset // PAGE_SIZE + 1
    total_pages = max(1, math.ceil(total / PAGE_SIZE))
    nav = []
    if offset > 0:
        nav.append(InlineKeyboardButton(
            text="⬅️",
            callback_data=f"vl:{ctx_short}:{ctx_id}:{offset - PAGE_SIZE}:{sort_by}",
        ))
    nav.append(InlineKeyboardButton(text=f"Стр. {page}/{total_pages}", callback_data="noop"))
    if offset + PAGE_SIZE < total:
        nav.append(InlineKeyboardButton(
            text="➡️",
            callback_data=f"vl:{ctx_short}:{ctx_id}:{offset + PAGE_SIZE}:{sort_by}",
        ))
    if nav:
        buttons.append(nav)

    text_block = "\n\n".join(text_lines)
    return text_block, buttons
```

- [ ] **Step 3: Update _show_list to use new text+buttons format**

Modify `_show_list` in browse_core.py. The call to `_clickable_list_buttons` now returns `(text_block, buttons)`:

```python
    items_text, buttons = _clickable_list_buttons(items, ctx_short, ctx_id, offset, total, deleting_item_id=deleting_item_id, sort_by=sort_by)
    if context_type == "category":
        buttons.insert(0, _sort_buttons(int(ctx_id), sort_by))
    elif context_type == "recent":
        buttons.insert(0, _recent_sort_buttons(sort_by))

    # Footer buttons
    footer = [_back_button_for_ctx(ctx_short, ctx_id)]
    if context_type == "category":
        footer.insert(0, InlineKeyboardButton(
            text="📨 Каналы",
            callback_data=f"cs:{ctx_id}:0",
        ))
    buttons.append(footer)

    full_text = f"{title}\n\n{items_text}"

    await callback.message.edit_text(
        full_text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )
    await callback.answer()
```

- [ ] **Step 4: Update cmd_recent and cmd_pinned in browse.py**

These use `_clickable_list_buttons` directly. Update to unpack tuple:

```python
# In cmd_recent (also fix: use count_items_in_context instead of loading all items):
    total = await queries.count_items_in_context(db, user_id, "recent")
    items_text, buttons = _clickable_list_buttons(items, "r", "0", 0, total)
    buttons.append([_back_button_for_ctx("r")])
    await message.reply(
        f"🕐 <b>Последние записи</b> ({total})\n\n{items_text}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )

# In cmd_pinned (also fix: use count_items_in_context):
    total = await queries.count_items_in_context(db, user_id, "pinned")
    items_text, buttons = _clickable_list_buttons(items, "p", "0", 0, total)
    buttons.append([_back_button_for_ctx("p")])
    await message.reply(
        f"📌 <b>Закреплённые записи</b> ({total})\n\n{items_text}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )
```

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/ -v`
Note failures — some test_browse tests will need updating in Task 7.

- [ ] **Step 6: Commit**

```bash
git add savebot/handlers/browse_core.py savebot/handlers/browse.py
git commit -m "feat: text-based item lists with number buttons"
```

---

### Task 4: Text-based search results

**Files:**
- Modify: `savebot/handlers/browse.py:895-909` (`cmd_search` results rendering)

- [ ] **Step 1: Rewrite search results rendering**

Replace the results section in `cmd_search` (browse.py, after `if not items: return`):

```python
    # Build text-based search results
    result_lines = []
    buttons = []
    for i, item in enumerate(items[:10], 1):
        result_lines.append(_format_item_list_entry(item, i))
        buttons.append(InlineKeyboardButton(
            text=str(i),
            callback_data=f"vi:r:0:{item['id']}",
        ))

    text = f"{search_info}🔍 <b>Результаты ({len(items)}):</b>\n\n"
    text += "\n\n".join(result_lines)

    kb = []
    if buttons:
        kb.append(buttons)

    await wait_msg.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb) if kb else None,
        parse_mode="HTML",
    )
```

- [ ] **Step 2: Add import for _format_item_list_entry**

In browse.py, add `_format_item_list_entry` to the import from browse_core:

```python
from savebot.handlers.browse_core import (
    PAGE_SIZE, _CTX_MAP, _CTX_REV, _CTX_TITLES, SORT_LABELS,
    _truncate_tag, _truncate_source, _format_item_short, _format_item_full,
    _format_item, _format_item_list_entry, _sort_buttons, _recent_sort_buttons,
    _clickable_list_buttons,
    _back_button_for_ctx, _categories_markup,
    _show_list, _show_item_view, _show_categories_msg,
    _extract_list_context,
)
```

- [ ] **Step 3: Run tests**

Run: `python -m pytest tests/ -v`

- [ ] **Step 4: Commit**

```bash
git add savebot/handlers/browse.py
git commit -m "feat: text-based search results with formatting"
```

---

### Task 5: Remove dead navigation code

**Files:**
- Modify: `savebot/handlers/browse.py` — remove handlers
- Modify: `savebot/handlers/browse_core.py` — remove functions
- Modify: `savebot/handlers/menu.py` — remove state handlers
- Modify: `savebot/handlers/browse_core.py:351-437` — remove collection button from item view

- [ ] **Step 1: Remove handlers from browse.py**

Delete these handler functions entirely:
- `on_hub` (bm:hub, line ~34)
- `on_category_menu` (cm:, line ~71)
- `on_category_latest` (cl:, line ~101)
- `on_hub_tags` (bm:tags, line ~155)
- `on_hub_map` (bm:map, line ~188)
- `on_hub_forgotten` (bm:forg, line ~228)
- `on_hub_sources` (bm:sources, line ~235)
- `on_hub_colls` (bm:colls, line ~295)
- `cmd_collections` (Command "collections", line ~300)
- `on_browse_collection` (bc:, line ~305)
- `on_hub_newcoll` (bm:newcoll, line ~314)
- `on_hub_newcat` (bm:newcat, line ~327)
- `on_tag_items` (tag_items:, line ~350)
- `on_tags_back` (tags_back, line ~358)
- `on_action_add_to_collection` (va:coll:, line ~751)
- `on_action_add_to_coll_confirm` (va:ac:, line ~776)
- `on_action_new_collection_for_item` (va:nc:, line ~794)

Replace `/tags` and `/collections` commands with stubs:
```python
@router.message(Command("tags"))
async def cmd_tags(message: types.Message, **kwargs):
    await message.reply("Эта команда больше не доступна. Используйте 📂 Все записи.")

@router.message(Command("collections"))
async def cmd_collections(message: types.Message, **kwargs):
    await message.reply("Эта команда больше не доступна. Используйте 📂 Все записи.")
```

Keep:
- `on_hub_cats` (bm:cats) — still used as "Все записи" callback
- `on_category_sources` (cs:) — channels within category
- `on_browse_source` (src:) — items from source
- `on_browse_category` (browse_cat:) — item list
- All `vi:`, `vn:`, `vl:`, `va:`, `vd:`, `vy:`, `vx:` handlers

- [ ] **Step 2: Remove dead functions from browse_core.py**

Delete:
- `_more_markup` function
- `_show_collections` function

- [ ] **Step 3: Remove collection button from item view**

In `_show_item_view` (browse_core.py), remove the collection button from actions2 row:

```python
    # Action row 2: tags, note, related (no collection)
    actions2 = []
    actions2.append(InlineKeyboardButton(text="🏷 Теги", callback_data=f"va:tags:{item_id}"))
    actions2.append(InlineKeyboardButton(text="✏️ Заметка", callback_data=f"va:note:{item_id}"))
    actions2.append(InlineKeyboardButton(text="🔗 Похожие", callback_data=f"va:rel:{item_id}"))
    buttons.append(actions2)
```

- [ ] **Step 4: Remove dead state handlers from menu.py**

Remove `new_browse_cat` state check (lines ~88-98) and `new_collection` state check (lines ~100-117) from `state_dispatcher`.

Remove these prefixes from the cleanup list in `handle_keyboard_button`:
```python
    for prefix in ("search_prompt_", "rename_cat_", "awaiting_", "edit_tags_", "edit_note_"):
        await delete_state(db, f"{prefix}{user_id}")
```

- [ ] **Step 5: Clean up imports in browse.py**

Remove unused imports: `_more_markup`, `_show_collections` from the browse_core import line.
**Note:** Keep `set_state` import — it's still used by `on_action_tags` and `on_action_note` handlers.

- [ ] **Step 6: Run tests**

Run: `python -m pytest tests/ -v`
Note all failures — they will be fixed in Task 7.

- [ ] **Step 7: Commit**

```bash
git add savebot/handlers/browse.py savebot/handlers/browse_core.py savebot/handlers/menu.py
git commit -m "refactor: remove dead navigation — tags, collections, map, hub, sub-menu"
```

---

### Task 6: Update tests

**Files:**
- Modify: `tests/test_architecture.py`
- Modify: `tests/test_browse.py`

- [ ] **Step 1: Update callback patterns in test_architecture.py**

Remove patterns for deleted features:
- `bc:*` (collections)
- `va:nc:*` (new collection from item)
- `va:ac:*` (add to collection from item)
- `va:coll:*` (collection picker from item)

Remove `cm:` pattern if present. Keep all others.

- [ ] **Step 2: Add new callback patterns if missing**

Ensure `cs:{cat_id}:0` pattern exists (channels in category).

- [ ] **Step 3: Update test_browse.py for new list format**

`_clickable_list_buttons` now returns `(text, buttons)` tuple. Update any tests that call it:

```python
# Old:
buttons = _clickable_list_buttons(items, "c", "1", 0, 5)
# New:
text, buttons = _clickable_list_buttons(items, "c", "1", 0, 5)
assert "item summary" in text
```

- [ ] **Step 4: Remove tests for deleted features**

Remove tests referencing:
- `_more_markup`
- `_show_collections`
- `on_hub_tags`
- `on_hub_map`
- Collection-related handlers

- [ ] **Step 5: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add tests/
git commit -m "test: update tests for navigation redesign"
```

---

### Task 7: AI-powered category cleanup

**Files:**
- Create: `savebot/services/ai_cleanup.py`
- Create: `savebot/handlers/cleanup.py`
- Modify: `savebot/handlers/settings.py`
- Modify: `savebot/bot.py`
- Create: `tests/test_cleanup.py`

- [ ] **Step 1: Create ai_cleanup.py service**

Create `savebot/services/ai_cleanup.py`:

```python
"""AI-powered category consolidation service."""
from __future__ import annotations

import json
import logging

from savebot.services.ai_classifier import _strip_code_blocks

logger = logging.getLogger(__name__)

CLEANUP_PROMPT = """\
Analyze these categories and their sample items. Suggest a consolidation plan.

Rules:
1. Keep the 7 default categories: Технологии, Финансы, Здоровье, Обучение, Работа, Творчество, Разное.
2. For each non-default category, suggest ONE action:
   - "merge" into a default or larger category (with reason)
   - "keep" if it has a clear distinct purpose and enough items
   - "delete" if empty (0 items)
3. For orphan items that don't fit any category well, suggest creating a new category ONLY if 3+ items share a theme.
4. Respond with ONLY valid JSON array.

JSON format:
[
  {"category": "Name", "action": "merge", "target": "Target Category", "reason": "..."},
  {"category": "Name", "action": "keep", "reason": "..."},
  {"category": "Name", "action": "delete", "reason": "empty"},
  {"action": "create", "name": "New Category", "emoji": "🎯", "items": [id1, id2, id3], "reason": "..."}
]
"""


async def analyze_categories(db, user_id: int) -> list[dict] | None:
    """Ask AI to analyze categories and suggest a consolidation plan."""
    from savebot.db import queries
    from savebot.services.ai_search import _call_openrouter

    categories = await queries.get_all_categories(db, user_id)
    if not categories:
        return None

    # Build context: categories with sample items
    context_parts = []
    for cat in categories:
        items = await queries.get_items_by_category(
            db, user_id, cat["id"], limit=5, offset=0,
        )
        sample = []
        for item in items:
            summary = item.get("ai_summary") or (item.get("content_text", "")[:80])
            tags = ", ".join(item.get("tags", []))
            sample.append(f"  - #{item['id']}: {summary} [{tags}]")

        header = f"{cat.get('emoji', '📁')} {cat['name']} ({cat.get('item_count', 0)} items)"
        if sample:
            context_parts.append(header + "\n" + "\n".join(sample))
        else:
            context_parts.append(header + "\n  (empty)")

    user_prompt = "Categories and sample items:\n\n" + "\n\n".join(context_parts)

    text = await _call_openrouter(CLEANUP_PROMPT, user_prompt, temperature=0.3, max_tokens=800)
    if not text:
        return None

    try:
        text = _strip_code_blocks(text)
        return json.loads(text)
    except (json.JSONDecodeError, TypeError) as e:
        logger.error("AI cleanup parse error: %s", e)
        return None
```

- [ ] **Step 2: Create cleanup.py handler**

Create `savebot/handlers/cleanup.py`:

```python
"""AI-powered category cleanup handlers."""
from __future__ import annotations

import html
import logging

from aiogram import F, Router, types
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from savebot.db import queries
from savebot.services.ai_cleanup import analyze_categories

router = Router()
logger = logging.getLogger(__name__)

# In-memory storage for pending cleanup plans (user_id -> list of suggestions)
_pending_plans: dict[int, list[dict]] = {}


@router.callback_query(F.data == "settings_cleanup")
async def on_cleanup_start(callback: types.CallbackQuery, db=None):
    """Start AI category analysis."""
    user_id = callback.from_user.id
    await callback.message.edit_text("🧹 <b>Анализирую категории...</b>", parse_mode="HTML")
    await callback.answer()

    plan = await analyze_categories(db, user_id)
    if not plan:
        await callback.message.edit_text(
            "⚠️ Не удалось проанализировать категории. Попробуйте позже.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Назад", callback_data="settings_back")],
            ]),
            parse_mode="HTML",
        )
        return

    _pending_plans[user_id] = plan
    await _show_next_suggestion(callback.message, user_id, 0)


async def _show_next_suggestion(message: types.Message, user_id: int, index: int):
    """Show the next suggestion in the cleanup plan."""
    plan = _pending_plans.get(user_id, [])

    if index >= len(plan):
        # All done
        del _pending_plans[user_id]
        await message.edit_text(
            "✅ <b>Уборка завершена!</b>",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 К настройкам", callback_data="settings_back")],
            ]),
            parse_mode="HTML",
        )
        return

    s = plan[index]
    action = s.get("action", "")
    reason = html.escape(s.get("reason", ""))

    if action == "merge":
        text = (
            f"🧹 <b>Предложение {index + 1}/{len(plan)}</b>\n\n"
            f"📂 <b>{html.escape(s['category'])}</b> → <b>{html.escape(s['target'])}</b>\n"
            f"Причина: {reason}"
        )
    elif action == "delete":
        text = (
            f"🧹 <b>Предложение {index + 1}/{len(plan)}</b>\n\n"
            f"🗑 Удалить: <b>{html.escape(s['category'])}</b>\n"
            f"Причина: {reason}"
        )
    elif action == "create":
        emoji = s.get("emoji", "📁")
        text = (
            f"🧹 <b>Предложение {index + 1}/{len(plan)}</b>\n\n"
            f"➕ Создать: {emoji} <b>{html.escape(s['name'])}</b>\n"
            f"Перенести {len(s.get('items', []))} записей\n"
            f"Причина: {reason}"
        )
    elif action == "keep":
        text = (
            f"🧹 <b>Предложение {index + 1}/{len(plan)}</b>\n\n"
            f"✅ Оставить: <b>{html.escape(s['category'])}</b>\n"
            f"Причина: {reason}"
        )
    else:
        # Skip unknown actions
        await _show_next_suggestion(message, user_id, index + 1)
        return

    buttons = [
        [
            InlineKeyboardButton(text="✅ Принять", callback_data=f"cleanup_yes:{index}"),
            InlineKeyboardButton(text="⏭ Пропустить", callback_data=f"cleanup_skip:{index}"),
        ],
        [InlineKeyboardButton(text="⏹ Закончить", callback_data="cleanup_done")],
    ]

    await message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")


@router.callback_query(F.data.startswith("cleanup_yes:"))
async def on_cleanup_accept(callback: types.CallbackQuery, db=None):
    """Accept a cleanup suggestion and execute it."""
    index = int(callback.data.split(":")[1])
    user_id = callback.from_user.id
    plan = _pending_plans.get(user_id, [])

    if index >= len(plan):
        await callback.answer("Ошибка")
        return

    s = plan[index]
    action = s.get("action", "")

    try:
        if action == "merge":
            source_cat = await queries.get_category_by_name(db, user_id, s["category"])
            target_cat = await queries.get_category_by_name(db, user_id, s["target"])
            if source_cat and target_cat:
                moved = await queries.merge_categories(db, user_id, source_cat["id"], target_cat["id"])
                await callback.answer(f"✅ Перенесено {moved} записей")
            else:
                await callback.answer("⚠️ Категория не найдена")

        elif action == "delete":
            cat = await queries.get_category_by_name(db, user_id, s["category"])
            if cat:
                await queries.delete_category(db, user_id, cat["id"])
                await callback.answer("✅ Удалено")
            else:
                await callback.answer("⚠️ Категория не найдена")

        elif action == "create":
            emoji = s.get("emoji", "📁")
            cat = await queries.get_or_create_category(db, user_id, s["name"], emoji)
            for item_id in s.get("items", []):
                await queries.update_item_category(db, user_id, item_id, cat["id"])
            await callback.answer(f"✅ Создано, перенесено {len(s.get('items', []))} записей")

        elif action == "keep":
            await callback.answer("✅ Оставлено")

    except Exception as e:
        logger.error("Cleanup action failed: %s", e)
        await callback.answer("⚠️ Ошибка при выполнении")

    await _show_next_suggestion(callback.message, user_id, index + 1)


@router.callback_query(F.data.startswith("cleanup_skip:"))
async def on_cleanup_skip(callback: types.CallbackQuery, db=None):
    """Skip a suggestion."""
    index = int(callback.data.split(":")[1])
    user_id = callback.from_user.id
    await callback.answer("⏭ Пропущено")
    await _show_next_suggestion(callback.message, user_id, index + 1)


@router.callback_query(F.data == "cleanup_done")
async def on_cleanup_done(callback: types.CallbackQuery, db=None):
    """End cleanup early."""
    user_id = callback.from_user.id
    _pending_plans.pop(user_id, None)
    await callback.message.edit_text(
        "✅ <b>Уборка завершена!</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 К настройкам", callback_data="settings_back")],
        ]),
        parse_mode="HTML",
    )
    await callback.answer()
```

- [ ] **Step 3: Add cleanup button to settings.py**

In `_render_settings`, add a cleanup button at the bottom of `rows`:

```python
    rows.append([InlineKeyboardButton(text="🧹 Умная уборка категорий", callback_data="settings_cleanup")])
```

- [ ] **Step 4: Register cleanup router in bot.py**

Add after settings router import/include:

```python
from savebot.handlers import cleanup
# In router registration section:
dp.include_router(cleanup.router)
```

Register AFTER settings but BEFORE manage.

- [ ] **Step 5: Update test_architecture.py**

Update `EXPECTED_ROUTER_ORDER`:
```python
EXPECTED_ROUTER_ORDER = ["settings", "cleanup", "manage", "menu", "browse", "inline", "save"]
```

Add callback patterns:
```python
    "cleanup_yes:99",
    "cleanup_skip:99",
    "cleanup_done",
    "settings_cleanup",
```

- [ ] **Step 6: Create basic test**

Create `tests/test_cleanup.py`:

```python
"""Tests for AI category cleanup."""
import pytest
from savebot.services.ai_cleanup import CLEANUP_PROMPT


class TestCleanupPrompt:
    def test_prompt_mentions_defaults(self):
        assert "Технологии" in CLEANUP_PROMPT
        assert "Разное" in CLEANUP_PROMPT

    def test_prompt_requires_json(self):
        assert "JSON" in CLEANUP_PROMPT
```

- [ ] **Step 7: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: ALL PASS

- [ ] **Step 8: Commit**

```bash
git add savebot/services/ai_cleanup.py savebot/handlers/cleanup.py savebot/handlers/settings.py savebot/bot.py tests/test_cleanup.py tests/test_architecture.py
git commit -m "feat: AI-powered category cleanup in settings"
```

---

## Summary

| Task | What | Risk |
|------|------|------|
| 1 | Keyboard 4 buttons | Low — isolated change |
| 2 | Direct category nav | Medium — rewires category flow |
| 3 | Text-based lists | Medium — changes core display |
| 4 | Text-based search | Low — isolated to cmd_search |
| 5 | Remove dead code | Medium — many deletions |
| 6 | Update tests | Low — follows from above |
| 7 | AI cleanup feature | Medium — new AI integration |

**Deploy after:** Task 6 (all navigation changes tested). Task 7 can be deployed separately.

## Known Limitations
- Removing "📌 Закрепленные" from keyboard is intentional — users can still access via /pinned command or 📌 sort within category.
- `_pending_plans` in cleanup.py is in-memory — lost on bot restart. Acceptable for v1.
- Old cached keyboards (with "Категории", "Закрепленные") handled via backward-compat routing in BUTTON_TEXTS.
