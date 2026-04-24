# Navigation UX Improvement — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce clicks to reach posts (4→3) and enable quick deletion from list view without losing context.

**Architecture:** All changes in one file (`browse.py`). Browse button shows categories directly (hub becomes a sub-menu). List view gains per-row delete buttons with inline confirmation. Delete from item view returns to list instead of hub.

**Tech Stack:** Python 3.12, aiogram 3, aiosqlite. Callback data max 64 bytes.

**Spec:** `docs/superpowers/specs/2026-03-16-navigation-ux-design.md`

---

## Chunk 1: All Changes

All work is in one file. Tasks are independent and can be done in parallel by separate agents.

### Task 1: Browse shows categories directly

**Files:**
- Modify: `savebot/handlers/browse.py`

This task changes Browse (button + command + callback) to show the category list immediately, and moves the old hub items behind an "Ещё" button.

- [ ] **Step 1: Rename hub to "more" sub-menu**

Rename `_hub_markup()` to `_more_markup()`. Remove the "📂 Категории" button from it (user is already in categories). Keep: Карта знаний, Забытые записи, Новая категория.

```python
def _more_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗺 Карта знаний", callback_data="bm:map")],
        [InlineKeyboardButton(text="🕸 Забытые записи", callback_data="bm:forg")],
        [InlineKeyboardButton(text="➕ Новая категория", callback_data="bm:newcat")],
        [InlineKeyboardButton(text="🔙 К категориям", callback_data="bm:cats")],
    ])
```

- [ ] **Step 2: Change `on_hub` callback to show "more" menu**

```python
@router.callback_query(F.data == "bm:hub")
async def on_hub(callback: types.CallbackQuery, db=None):
    await callback.message.edit_text(
        "📋 <b>Дополнительно</b>",
        reply_markup=_more_markup(),
        parse_mode="HTML",
    )
    await callback.answer()
```

- [ ] **Step 3: Make `cmd_browse` and the `bm:cats` callback both show category list**

Extract category list rendering into a helper `_show_categories` that works for both Message and CallbackQuery:

```python
async def _show_categories_msg(message: types.Message, db=None):
    """Show category list as a new message (for commands/keyboard buttons)."""
    if db is None:
        db = message.bot.get("db")
    user_id = message.from_user.id
    categories = await queries.get_all_categories(db, user_id)

    buttons = []
    for cat in categories:
        emoji = cat.get("emoji", "📁")
        buttons.append([InlineKeyboardButton(
            text=f"{emoji} {cat['name']} ({cat['item_count']})",
            callback_data=f"browse_cat:{cat['id']}:0",
        )])
    # Footer: Tags + More
    buttons.append([
        InlineKeyboardButton(text="🏷 Теги", callback_data="bm:tags"),
        InlineKeyboardButton(text="📋 Ещё", callback_data="bm:hub"),
    ])

    await message.reply(
        "📂 <b>Категории:</b>" if categories else "📂 <b>Категорий пока нет.</b>\n\nНажмите «Ещё» → «Новая категория».",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )
```

Update `cmd_browse`:

```python
@router.message(Command("browse"))
async def cmd_browse(message: types.Message, db=None):
    await _show_categories_msg(message, db=db)
```

Update `on_hub_cats` to reuse the same layout but via `edit_text`:

```python
@router.callback_query(F.data == "bm:cats")
async def on_hub_cats(callback: types.CallbackQuery, db=None):
    user_id = callback.from_user.id
    categories = await queries.get_all_categories(db, user_id)

    buttons = []
    for cat in categories:
        emoji = cat.get("emoji", "📁")
        buttons.append([InlineKeyboardButton(
            text=f"{emoji} {cat['name']} ({cat['item_count']})",
            callback_data=f"browse_cat:{cat['id']}:0",
        )])
    buttons.append([
        InlineKeyboardButton(text="🏷 Теги", callback_data="bm:tags"),
        InlineKeyboardButton(text="📋 Ещё", callback_data="bm:hub"),
    ])

    await callback.message.edit_text(
        "📂 <b>Категории:</b>" if categories else "📂 <b>Категорий пока нет.</b>\n\nНажмите «Ещё» → «Новая категория».",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )
    await callback.answer()
```

- [ ] **Step 4: Update `_back_button_for_ctx`**

The "Browse" back button should now go to `bm:cats` (category list) instead of `bm:hub`:

```python
def _back_button_for_ctx(ctx_short: str) -> InlineKeyboardButton:
    if ctx_short == "c":
        return InlineKeyboardButton(text="🔙 К категориям", callback_data="bm:cats")
    elif ctx_short == "t":
        return InlineKeyboardButton(text="🔙 К тегам", callback_data="bm:tags")
    else:
        return InlineKeyboardButton(text="🔙 К категориям", callback_data="bm:cats")
```

- [ ] **Step 5: Commit**

```bash
git add savebot/handlers/browse.py
git commit -m "feat: browse shows categories directly, hub moved behind 'More' button"
```

---

### Task 2: Quick delete from list view

**Files:**
- Modify: `savebot/handlers/browse.py`

Adds a 🗑 button per row in list views and inline confirmation/cancel.

New callback prefixes:
- `vd:{ctx_short}:{ctx_id}:{item_id}:{offset}` — initiate delete (show confirmation)
- `vy:{ctx_short}:{ctx_id}:{item_id}:{offset}` — confirm delete
- `vx:{ctx_short}:{ctx_id}:{offset}` — cancel delete (return to list)

Max callback data: `vd:t:some_20char_tag_here:99999:99999` = ~42 bytes. Under 64 limit.

- [ ] **Step 1: Modify `_clickable_list_buttons` to add 🗑 per row**

```python
def _clickable_list_buttons(
    items: list[dict],
    ctx_short: str,
    ctx_id: str | int,
    offset: int,
    total: int,
    deleting_item_id: int | None = None,
) -> list[list[InlineKeyboardButton]]:
    """Build clickable item buttons + pagination for a list view.

    If deleting_item_id is set, that row shows confirm/cancel instead.
    """
    buttons = []
    for item in items:
        if deleting_item_id and item["id"] == deleting_item_id:
            # Confirmation row
            buttons.append([
                InlineKeyboardButton(
                    text=f"Удалить #{item['id']}?",
                    callback_data="noop",
                ),
                InlineKeyboardButton(
                    text="✅",
                    callback_data=f"vy:{ctx_short}:{ctx_id}:{item['id']}:{offset}",
                ),
                InlineKeyboardButton(
                    text="❌",
                    callback_data=f"vx:{ctx_short}:{ctx_id}:{offset}",
                ),
            ])
        else:
            num = item.get("display_num", item["id"])
            title = _format_item_short(item)
            buttons.append([
                InlineKeyboardButton(
                    text=f"{num}. {title}",
                    callback_data=f"vi:{ctx_short}:{ctx_id}:{item['id']}",
                ),
                InlineKeyboardButton(
                    text="🗑",
                    callback_data=f"vd:{ctx_short}:{ctx_id}:{item['id']}:{offset}",
                ),
            ])

    # Pagination row
    page = offset // PAGE_SIZE + 1
    total_pages = max(1, math.ceil(total / PAGE_SIZE))
    nav = []
    if offset > 0:
        nav.append(InlineKeyboardButton(
            text="⬅️",
            callback_data=f"vl:{ctx_short}:{ctx_id}:{offset - PAGE_SIZE}",
        ))
    nav.append(InlineKeyboardButton(text=f"Стр. {page}/{total_pages}", callback_data="noop"))
    if offset + PAGE_SIZE < total:
        nav.append(InlineKeyboardButton(
            text="➡️",
            callback_data=f"vl:{ctx_short}:{ctx_id}:{offset + PAGE_SIZE}",
        ))
    if nav:
        buttons.append(nav)

    return buttons
```

- [ ] **Step 2: Add delete initiation handler**

```python
@router.callback_query(F.data.startswith("vd:"))
async def on_list_delete(callback: types.CallbackQuery, db=None):
    """Show inline delete confirmation in list view."""
    parts = callback.data.split(":")
    ctx_short = parts[1]
    ctx_id = parts[2]
    item_id = int(parts[3])
    offset = int(parts[4])
    context_type = _CTX_REV.get(ctx_short, "recent")
    await _show_list(callback, context_type, ctx_id, offset, db=db, deleting_item_id=item_id)
```

- [ ] **Step 3: Add delete confirm handler**

```python
@router.callback_query(F.data.startswith("vy:"))
async def on_list_delete_confirm(callback: types.CallbackQuery, db=None):
    """Confirm delete from list view — delete and refresh list."""
    parts = callback.data.split(":")
    ctx_short = parts[1]
    ctx_id = parts[2]
    item_id = int(parts[3])
    offset = int(parts[4])
    user_id = callback.from_user.id

    deleted = await queries.delete_item(db, user_id, item_id)
    if deleted:
        await callback.answer("🗑 Удалено")
    else:
        await callback.answer("Запись не найдена.")

    # Refresh list at same offset (adjust if page is now empty)
    context_type = _CTX_REV.get(ctx_short, "recent")
    if context_type == "category":
        remaining = await queries.count_items_in_category(db, user_id, int(ctx_id))
    elif context_type == "tag":
        remaining = await queries.count_items_by_tag(db, user_id, str(ctx_id))
    else:
        all_items = await queries.get_items_page_with_nums(
            db, user_id, context_type, context_id=None, limit=10000, offset=0,
        )
        remaining = len(all_items)

    # If offset is beyond remaining items, go back one page
    if offset >= remaining and offset > 0:
        offset = max(0, offset - PAGE_SIZE)

    if remaining == 0:
        await callback.message.edit_text(
            "📂 Список пуст.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [_back_button_for_ctx(ctx_short)]
            ]),
            parse_mode="HTML",
        )
        return

    await _show_list(callback, context_type, ctx_id, offset, db=db)
```

- [ ] **Step 4: Add delete cancel handler**

```python
@router.callback_query(F.data.startswith("vx:"))
async def on_list_delete_cancel(callback: types.CallbackQuery, db=None):
    """Cancel delete — refresh list normally."""
    parts = callback.data.split(":")
    ctx_short = parts[1]
    ctx_id = parts[2]
    offset = int(parts[3])
    context_type = _CTX_REV.get(ctx_short, "recent")
    await callback.answer("Отменено")
    await _show_list(callback, context_type, ctx_id, offset, db=db)
```

- [ ] **Step 5: Update `_show_list` to accept `deleting_item_id`**

Add parameter `deleting_item_id: int | None = None` to `_show_list` and pass it through to `_clickable_list_buttons`:

```python
async def _show_list(callback, context_type, ctx_id, offset, db=None, deleting_item_id=None):
    # ... existing code ...
    buttons = _clickable_list_buttons(items, ctx_short, ctx_id, offset, total, deleting_item_id=deleting_item_id)
    # ... rest unchanged ...
```

- [ ] **Step 6: Commit**

```bash
git add savebot/handlers/browse.py
git commit -m "feat: quick delete from list view with inline confirmation"
```

---

### Task 3: Fix post-delete context loss

**Files:**
- Modify: `savebot/handlers/browse.py`

Currently `on_action_delete_confirm` and `on_action_delete_cancel` both send user to hub. Fix them to return to list / item view using context extracted from the inline keyboard.

- [ ] **Step 1: Fix `on_action_delete_confirm` — return to list after delete**

Replace the current "go to hub" behavior. Extract context from keyboard buttons (find the `vl:` back-to-list button):

```python
@router.callback_query(F.data.startswith("va:dyes:"))
async def on_action_delete_confirm(callback: types.CallbackQuery, db=None):
    item_id = int(callback.data.split(":")[2])
    user_id = callback.from_user.id

    # Extract list context from the keyboard before deleting
    ctx_short, ctx_id, offset = "r", "0", 0
    kb = callback.message.reply_markup
    if kb and kb.inline_keyboard:
        for row in kb.inline_keyboard:
            for btn in row:
                if btn.callback_data and btn.callback_data.startswith("vl:"):
                    parts = btn.callback_data.split(":")
                    ctx_short = parts[1]
                    ctx_id = parts[2]
                    offset = int(parts[3])
                    break

    deleted = await queries.delete_item(db, user_id, item_id)
    if deleted:
        await callback.answer("🗑 Удалено")
    else:
        await callback.answer("Запись не найдена.")
        return

    # Return to list (adjust offset if needed)
    context_type = _CTX_REV.get(ctx_short, "recent")
    if context_type == "category":
        remaining = await queries.count_items_in_category(db, user_id, int(ctx_id))
    elif context_type == "tag":
        remaining = await queries.count_items_by_tag(db, user_id, str(ctx_id))
    else:
        all_items = await queries.get_items_page_with_nums(
            db, user_id, context_type, context_id=None, limit=10000, offset=0,
        )
        remaining = len(all_items)

    if offset >= remaining and offset > 0:
        offset = max(0, offset - PAGE_SIZE)

    if remaining == 0:
        await callback.message.edit_text(
            "📂 Список пуст.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [_back_button_for_ctx(ctx_short)]
            ]),
            parse_mode="HTML",
        )
        return

    await _show_list(callback, context_type, ctx_id, offset, db=db)
```

- [ ] **Step 2: Fix `on_action_delete_cancel` — return to item view**

```python
@router.callback_query(F.data.startswith("va:dno:"))
async def on_action_delete_cancel(callback: types.CallbackQuery, db=None):
    item_id = int(callback.data.split(":")[2])
    await callback.answer("Отменено")

    # Find context and return to item view
    ctx_short, ctx_id = "r", "0"
    kb = callback.message.reply_markup
    if kb and kb.inline_keyboard:
        for row in kb.inline_keyboard:
            for btn in row:
                if btn.callback_data and btn.callback_data.startswith("vl:"):
                    parts = btn.callback_data.split(":")
                    ctx_short = parts[1]
                    ctx_id = parts[2]
                    break

    await _show_item_view(callback, ctx_short, ctx_id, item_id, db=db)
```

Note: The delete confirmation screen (`on_action_delete` / `va:del:`) currently doesn't preserve context in its buttons. We need to fix it to pass context through.

- [ ] **Step 3: Fix `on_action_delete` to preserve context in confirmation buttons**

The problem: `va:del:{item_id}` doesn't carry context. We need to encode context into the confirmation buttons. Since the delete is initiated from item view which HAS context in its keyboard, extract it there:

```python
@router.callback_query(F.data.startswith("va:del:"))
async def on_action_delete(callback: types.CallbackQuery, db=None):
    item_id = int(callback.data.split(":")[2])

    # Extract context from current keyboard
    ctx_short, ctx_id, offset = "r", "0", 0
    kb = callback.message.reply_markup
    if kb and kb.inline_keyboard:
        for row in kb.inline_keyboard:
            for btn in row:
                if btn.callback_data and btn.callback_data.startswith("vl:"):
                    parts = btn.callback_data.split(":")
                    ctx_short = parts[1]
                    ctx_id = parts[2]
                    offset = int(parts[3])
                    break

    buttons = [
        [
            InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"va:dyes:{item_id}"),
            InlineKeyboardButton(text="❌ Отмена", callback_data=f"va:dno:{item_id}"),
        ],
        # Hidden context carrier for confirm/cancel handlers
        [InlineKeyboardButton(text="🔙 К списку", callback_data=f"vl:{ctx_short}:{ctx_id}:{offset}")],
    ]
    await callback.message.edit_text(
        f"🗑 Удалить запись #{item_id}?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )
    await callback.answer()
```

This adds a visible "К списку" back button to the confirmation screen (useful if user changes mind entirely) AND serves as a context carrier for the confirm/cancel handlers.

- [ ] **Step 4: Commit**

```bash
git add savebot/handlers/browse.py
git commit -m "fix: delete from item view returns to list instead of hub"
```

---

### Task 4: Deploy and verify

- [ ] **Step 1: Deploy to server**

Follow deploy procedure from memory (`reference_server.md`).

- [ ] **Step 2: Verify in Telegram**

Test these flows:
1. Press "📂 Browse" → should show category list directly (no hub)
2. Category list should have "🏷 Теги" and "📋 Ещё" at bottom
3. "📋 Ещё" → should show Map, Forgotten, New Category
4. In a category list, press 🗑 next to a post → should show inline confirmation
5. Confirm delete → post gone, list refreshes in place
6. Cancel delete → list returns to normal
7. Open a post → Delete → Confirm → should return to list, not hub
8. Open a post → Delete → Cancel → should return to post view
