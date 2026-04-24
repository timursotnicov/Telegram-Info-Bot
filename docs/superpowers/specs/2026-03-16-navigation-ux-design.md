# Navigation UX Improvement

## Problem

1. Too many clicks to reach a post via Browse (4 clicks: Browse → Hub → Categories → Category → Post)
2. Deleting multiple posts in a category is painful — must open each post, delete, confirm, get kicked to hub, navigate back

## Solution

### Change 1: Browse shows categories directly

- "📂 Browse" button and `/browse` command skip the hub and show the **category list** immediately
- At the bottom of the category list, two extra buttons:
  - `🏷 Теги` — opens tag cloud (currently in hub)
  - `📋 Ещё` — opens sub-menu with: Карта знаний, Забытые записи, Новая категория
- Result: Browse → Category → Post = **3 clicks** (was 4)

### Change 2: Quick delete from list view

- Each post row in a list gets a `🗑` delete button next to it
- Layout: `[post title] [🗑]` — two buttons per row
- Delete flow:
  1. User taps 🗑
  2. List redraws — that post's row becomes: `Удалить #id? [✅ Да] [❌ Нет]`
  3. **Yes**: post deleted, list refreshes in place (same page)
  4. **No**: list returns to normal view
- Callback data format for delete button: `vd:{ctx_short}:{ctx_id}:{item_id}:{offset}` (vd = view delete)
- Callback data for confirm: `vy:{ctx_short}:{ctx_id}:{item_id}:{offset}` (vy = yes delete)
- Callback data for cancel: `vx:{ctx_short}:{ctx_id}:{item_id}:{offset}` (vx = cancel delete)

### Change 3: Fix post-delete context loss

- After deleting from item view (`va:dyes`), return to list (using context from keyboard buttons) instead of hub
- After canceling delete (`va:dno`), return to item view instead of hub

## Files to modify

- `savebot/handlers/browse.py` — all changes are here:
  - `_hub_markup()` → becomes `_more_markup()` for the "Ещё" sub-menu
  - `cmd_browse()` / `on_hub()` → show category list directly
  - `_clickable_list_buttons()` → add 🗑 button per row
  - New handlers: `on_list_delete`, `on_list_delete_confirm`, `on_list_delete_cancel`
  - `on_action_delete_confirm()` → return to list instead of hub
  - `on_action_delete_cancel()` → return to item view instead of hub

## What stays unchanged

- Persistent keyboard (6 buttons)
- Recent, Pinned, Read List shortcuts (2 clicks)
- Item view layout and actions
- Search, Ask, inline query
