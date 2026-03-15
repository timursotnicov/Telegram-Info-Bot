# Anti-pattern: Unbounded Text in Callback Data

## The Problem
Telegram enforces a **64-byte limit** on `callback_data`. Putting user-generated
content (full tag names, category names, text snippets) directly into callbacks
will silently break when the content is too long.

## Bad Examples
```python
# BAD: full tag name can be arbitrarily long
callback_data=f"tag_items:{tag['tag']}:0"

# BAD: category name in callback
callback_data=f"cat_view:{category['name']}:0"

# BAD: item text in callback
callback_data=f"item:{item['content_text'][:50]}"
```

## Good Examples
```python
# GOOD: use numeric IDs for categories
callback_data=f"browse_cat:{cat['id']}:0"

# GOOD: truncate tags to fixed max length
callback_data=f"tag_items:{_truncate_tag(tag, 20)}:0"

# GOOD: reference items by ID only
callback_data=f"vi:c:5:{item['id']}"
```

## Rules
1. **Use numeric IDs** whenever possible (categories, items).
2. **Truncate strings** to a fixed max length (tags: 20 chars).
3. **Never put user text** (content, summaries, URLs) in callbacks.
4. **Test callback length**: `assert len(callback_data.encode()) <= 64`.
5. **Keep prefixes short**: 2-3 chars + colon (e.g., `vi:`, `va:`, `vl:`).

## State Store Alternative
For complex flows needing more context than fits in 64 bytes, use the state
store (`set_state` / `get_state` in `savebot/db/state_store.py`). Store the
full context in state and reference it by a short key in the callback.
