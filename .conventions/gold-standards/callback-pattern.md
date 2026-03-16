# Callback Data Naming Conventions

## Hard Limit
Telegram callback_data max = **64 bytes**. All callback strings MUST stay under this.

## Prefix Convention
Use 2-3 character prefixes + colon separator:

| Prefix | Meaning | Example |
|--------|---------|---------|
| `bm:` | Browse menu hub | `bm:cats`, `bm:tags`, `bm:map` |
| `vi:` | View item (single) | `vi:c:5:42` |
| `vn:` | View navigate (prev/next) | `vn:c:5:43` |
| `vl:` | View list (paginate) | `vl:c:5:10` |
| `va:` | View action (on item) | `va:pin:42`, `va:del:42`, `va:tags:42` |
| `browse_cat:` | Category items list | `browse_cat:5:0` |
| `tag_items:` | Tag items list | `tag_items:ai:0` |
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

## Pattern
```
prefix:context:context_id:item_id
```

Examples:
- `vi:c:5:42` — view item #42 in category 5
- `vn:t:ai:43` — navigate to item #43 in tag "ai"
- `vl:r:0:10` — recent list, offset 10
- `va:mc:42:5` — move item #42 to category 5

## Tag Truncation
Tags in callback data are truncated to 20 characters using `_truncate_tag()`.
This ensures `tag_items:{tag}:{offset}` stays well under 64 bytes.

## Static Callbacks
- `noop` — placeholder for non-interactive buttons (e.g., page counter)
- `browse_back` — return to category list
- `tags_back` — return to tag cloud
- `bm:hub` — return to browse hub
