# Anti-pattern: Item Titles in Button Labels

## The Problem
Putting item summaries/titles as inline keyboard button text wastes space,
limits content visibility, and makes lists hard to read. Buttons have a
practical text limit of ~40 characters.

## Bad Example
```python
# BAD: item content crammed into button text
buttons.append([InlineKeyboardButton(
    text=f"{num}. {title[:35]}...",
    callback_data=f"vi:c:5:{item['id']}",
)])
```

## Good Example
```python
# GOOD: text-based list + number buttons
text_lines.append(_format_item_list_entry(item, display_i))
number_buttons.append(InlineKeyboardButton(
    text=str(display_i),
    callback_data=f"vi:{ctx_short}:{ctx_id}:{item['id']}",
))
```

## Rules
1. Use `_text_list_with_buttons()` for all new item lists.
2. Items displayed as formatted text (title + meta line).
3. Navigation via number button row `[1][2][3][4][5]`.
4. Title max 80 chars, meta max 60 chars.
5. Total message text must stay under 4096 chars (Telegram limit).
6. See `gold-standards/text-list-format.py` for the full pattern.
