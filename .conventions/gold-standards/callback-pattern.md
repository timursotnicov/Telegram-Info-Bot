# Callback Data Naming Conventions

## Hard Limit
Telegram callback_data max = **64 bytes**. All callback strings MUST stay under this.

## Prefix Convention
Use 2-3 character prefixes + colon separator:

| Prefix | Meaning | Example |
|--------|---------|---------|
| `bm:` | Browse menu (cats, tags, more) | `bm:cats`, `bm:tags`, `bm:hub` |
| `vi:` | View item (single) | `vi:c:5:42` |
| `vn:` | View navigate (prev/next) | `vn:c:5:43` |
| `vl:` | View list (paginate) | `vl:c:5:10` |
| `va:` | View action (on item) | `va:pin:42`, `va:del:42`, `va:tags:42`, `va:rel:42`, `va:coll:42` |
| `vd:` | View delete (initiate from list) | `vd:c:5:42:0` |
| `vy:` | View delete yes (confirm) | `vy:c:5:42:0` |
| `vx:` | View delete cancel | `vx:c:5:0` |
| `browse_cat:` | Category items list | `browse_cat:5:0` |
| `tag_items:` | Tag items list | `tag_items:ai:0` |
| `bc:` | Browse collection items | `bc:3:0` |
| `settings_*` | Settings toggles | `settings_toggle:auto_save` |
| `save_*` | Save flow actions | `save_confirm:key123` |

## Context Short Codes
For navigation callbacks (`vi:`, `vn:`, `vl:`), the second segment is a context:

| Code | Context Type | ctx_id contains |
|------|-------------|-----------------|
| `c` | category | category ID (int) |
| `t` | tag | tag name (truncated to 20 chars) |
| `r` | recent | `0` (unused) |
| `p` | pinned | `0` (unused) |
| `l` | readlist | `0` (unused) |
| `f` | forgotten | `0` (unused) |
| `o` | collection | collection ID (int) |

## Pattern
```
prefix:context:context_id:item_id
```

Examples:
- `vi:c:5:42` — view item #42 in category 5
- `vn:t:ai:43` — navigate to item #43 in tag "ai"
- `vl:r:0:10` — recent list, offset 10
- `va:mc:42:5` — move item #42 to category 5
- `va:rel:42` — show related items for item #42
- `va:coll:42` — show collection picker for item #42
- `va:ac:42:3` — add item #42 to collection 3
- `va:nc:42` — create new collection and add item #42

## Tag Truncation
Tags in callback data are truncated to 20 characters using `_truncate_tag()`.
This ensures `tag_items:{tag}:{offset}` stays well under 64 bytes.

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
def _extract_list_context(callback: types.CallbackQuery) -> tuple[str, str, int] | None:
    kb = callback.message.reply_markup
    if kb and kb.inline_keyboard:
        for row in kb.inline_keyboard:
            for btn in row:
                if btn.callback_data and btn.callback_data.startswith("vl:"):
                    parts = btn.callback_data.split(":")
                    return parts[1], parts[2], int(parts[3])
    return None
```

This is used by item-view actions (pin, delete, read) that need to return
to the correct list page after completing.

## Static Callbacks
- `noop` — placeholder for non-interactive buttons (e.g., page counter)
- `bm:cats` — return to category list (main browse screen)
- `tags_back` — return to tag cloud
- `bm:hub` — open "More" menu (map, forgotten, new category, collections)
- `bm:colls` — open collections list
- `bm:newcoll` — create new collection prompt
