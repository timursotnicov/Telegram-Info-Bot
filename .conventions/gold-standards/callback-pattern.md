# Callback Data Naming Conventions

## Hard Limit
Telegram callback_data max = **64 bytes**. All callback strings MUST stay under this.

## Prefix Convention
Use 2-3 character prefixes + colon separator:

| Prefix | Meaning | Example |
|--------|---------|---------|
| `bm:` | Browse menu (cats only) | `bm:cats` |
| `vi:` | View item (single) | `vi:c:5:42` |
| `vn:` | View navigate (prev/next) | `vn:c:5:43` |
| `vl:` | View list (paginate) | `vl:c:5:10` |
| `va:` | View action (on item) | `va:pin:42`, `va:del:42`, `va:tags:42`, `va:rel:42` |
| `vd:` | View delete (initiate from list) | `vd:c:5:42:0` |
| `vy:` | View delete yes (confirm) | `vy:c:5:42:0` |
| `vx:` | View delete cancel | `vx:c:5:0` |
| `browse_cat:` | Category items list | `browse_cat:5:0` |
| `cs:` | Category sources (channels) | `cs:5:0` |
| `src:` | Source items list | `src:channel_name:0` |
| `settings_*` | Settings toggles | `settings_toggle:auto_save`, `settings_toggle:daily_brief_enabled` |
| `settings_brief_time:` | Daily brief time picker | `settings_brief_time:09:00` |
| `settings_cleanup` | Start AI category cleanup | `settings_cleanup` |
| `cleanup_*` | Cleanup flow actions | `cleanup_yes:0`, `cleanup_skip:0`, `cleanup_done` |
| `save_*` | Save flow actions | `save_confirm:key123` |

## Context Short Codes
For navigation callbacks (`vi:`, `vn:`, `vl:`), the second segment is a context:

| Code | Context Type | ctx_id contains |
|------|-------------|-----------------|
| `c` | category | category ID (int) |
| `t` | tag | tag name (truncated to 20 chars) |
| `r` | recent | `0` (unused) |
| `p` | pinned | `0` (unused) |
| `s` | source | source name (truncated) |

## Pattern
```
prefix:context:context_id:item_id
```

Examples:
- `vi:c:5:42` — view item #42 in category 5
- `vl:r:0:10` — recent list, offset 10
- `va:mc:42:5` — move item #42 to category 5
- `va:rel:42` — show related items for item #42

## Inline Delete Pattern (vd → vy/vx)
List-level delete uses a 3-step flow:
1. `vd:` — user taps trash icon, row is replaced with confirm/cancel buttons
2. `vy:` — user confirms, item is deleted, list refreshes
3. `vx:` — user cancels, list re-renders without confirmation

Format: `vd:{ctx_short}:{ctx_id}:{item_id}:{offset}`
The offset is carried through so the list can refresh to the correct page.

## Extract Context from Keyboard Pattern
When a callback handler needs navigation context (ctx_short, ctx_id, offset)
but it's not in its own callback_data, extract it from the `vl:` back button
in the current inline keyboard:

```python
def _extract_list_context(callback: types.CallbackQuery) -> tuple[str, str, int, str] | None:
    kb = callback.message.reply_markup
    if kb and kb.inline_keyboard:
        for row in kb.inline_keyboard:
            for btn in row:
                if btn.callback_data and btn.callback_data.startswith("vl:"):
                    parts = btn.callback_data.split(":")
                    sort_by = parts[4] if len(parts) > 4 else "d"
                    return parts[1], parts[2], int(parts[3]), sort_by
    return None
```

This is used by item-view actions (pin, delete, read) that need to return
to the correct list page after completing.

## Static Callbacks
- `noop` — placeholder for non-interactive buttons (e.g., page counter, delete placeholder)
- `bm:cats` — return to category list (main "Все записи" screen)
- `settings_cleanup` — start AI category cleanup
- `cleanup_done` — end cleanup early
- `settings_back` — return to settings from sub-screen
- `settings_brief_time` — open daily brief time picker
- `settings_brief_time:{HH:MM}` — set daily brief time

## Cleanup Flow Callbacks
- `settings_cleanup` — start AI analysis
- `cleanup_yes:{index}` — accept suggestion at index
- `cleanup_skip:{index}` — skip suggestion at index
- `cleanup_done` — end cleanup early
