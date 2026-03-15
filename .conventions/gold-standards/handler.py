"""Gold standard: handler module pattern.

Every handler module follows this structure:
1. Imports (aiogram, queries, state_store)
2. Router instance
3. Constants
4. Private helpers (prefixed with _)
5. Command handlers (@router.message(Command(...)))
6. Callback query handlers (@router.callback_query(F.data.startswith(...)))
"""

from __future__ import annotations

from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from savebot.db import queries

router = Router()


# ── Constants at module level ─────────────────────────────
PAGE_SIZE = 5


# ── Private helpers (underscore prefix) ───────────────────

def _format_something(item: dict) -> str:
    """Helpers are sync unless they need DB access."""
    return item.get("name", "")


# ── Command handler ───────────────────────────────────────
# - Always accept db=None as keyword arg (injected by middleware)
# - user_id = message.from_user.id as first line
# - Query DB, build text + markup, reply

@router.message(Command("example"))
async def cmd_example(message: types.Message, db=None):
    user_id = message.from_user.id
    items = await queries.get_recent_items(db, user_id)

    if not items:
        await message.reply("Nothing found.")
        return

    buttons = [[InlineKeyboardButton(text="Click", callback_data="example:1")]]
    await message.reply(
        "Result",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )


# ── Callback query handler ───────────────────────────────
# - Match with F.data.startswith("prefix:")
# - Parse parts = callback.data.split(":")
# - Always call callback.answer() (before or after edit)
# - Use callback.message.edit_text() to update in-place

@router.callback_query(F.data.startswith("example:"))
async def on_example(callback: types.CallbackQuery, db=None):
    parts = callback.data.split(":")
    item_id = int(parts[1])
    user_id = callback.from_user.id

    # ... do work ...

    await callback.message.edit_text("Updated", parse_mode="HTML")
    await callback.answer()
