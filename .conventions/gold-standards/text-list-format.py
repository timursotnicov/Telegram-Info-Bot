"""Gold standard: text-based list format pattern.

Item lists use text for content and number buttons for navigation.
This replaced the old pattern of putting item titles in button labels.

Layout:
    Title (category name + count)

    1. Item summary text
       📁 Category · 📨 Source · 2026-01-01 · #tag1 #tag2

    2. Item summary text
       📁 Category · 2026-01-15

    [1] [2] [3] [4] [5]        ← number buttons
    [⬅️] [Стр. 1/3] [➡️]      ← pagination
    [📨 Каналы] [🔙 Все записи] ← footer (category context)

Rules:
1. Use _text_list_with_buttons() — returns (text_block, buttons) tuple
2. Do NOT use _clickable_list_buttons() for new code (legacy only)
3. Title truncation: max 80 chars, then "..."
4. Meta line truncation: max 60 chars, then "..."
5. Total message must stay under 4096 chars (Telegram limit)
6. Number buttons in a single row: [1][2][3][4][5]
7. Delete flow: noop placeholder in number row + confirm/cancel below

Anti-pattern: Do NOT put item content in button labels.
"""

from __future__ import annotations

import html
import math

from aiogram.types import InlineKeyboardButton


PAGE_SIZE = 5


def _format_item_list_entry(item: dict, num: int) -> str:
    """Format a single item for text-based list view.

    Truncation: title <= 80 chars, meta <= 60 chars.
    """
    # Title from ai_summary or content_text
    if item.get("ai_summary"):
        title = item["ai_summary"]
    elif item.get("content_text"):
        title = item["content_text"][:120]
    else:
        title = "(без текста)"
    if len(title) > 80:
        title = title[:77] + "..."
    title = html.escape(title)

    line = f"<b>{num}.</b> {title}"

    # Meta line: category + source + date + tags (max 60 chars)
    meta_parts = []
    if item.get("category_emoji") and item.get("category_name"):
        meta_parts.append(f"{item['category_emoji']} {html.escape(item['category_name'])}")
    if item.get("source"):
        meta_parts.append(f"📨 {html.escape(item['source'])}")
    if item.get("created_at"):
        date_str = str(item["created_at"])[:10]
        meta_parts.append(date_str)

    tags = item.get("tags", [])
    if tags:
        meta_parts.append(" ".join(f"#{t}" for t in tags[:3]))

    if meta_parts:
        meta = " · ".join(meta_parts)
        if len(meta) > 60:
            meta = meta[:57] + "..."
        line += f"\n   {meta}"

    return line


def _text_list_with_buttons(
    items: list[dict],
    ctx_short: str,
    ctx_id: str | int,
    offset: int,
    total: int,
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
        display_i = i + 1
        text_lines.append(_format_item_list_entry(item, display_i))
        number_buttons.append(InlineKeyboardButton(
            text=str(display_i),
            callback_data=f"vi:{ctx_short}:{ctx_id}:{item['id']}",
        ))

    # Number buttons row
    if number_buttons:
        buttons.append(number_buttons)

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
