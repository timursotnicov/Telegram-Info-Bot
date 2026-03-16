"""Gold standard: state management pattern.

The state pattern enables multi-step interactions (e.g. prompting the user
for text input and processing it later). It uses the state_store module
(savebot/db/state_store.py) with set_state / get_state / delete_state.

Flow:
1. Callback handler sets state and shows a prompt
2. User types free text
3. state_dispatcher (menu.py) checks for pending states, dispatches to action
4. State is deleted after action completes

Key rules:
- State keys follow the pattern: f"{state_type}_{user_id}"
- state_dispatcher in menu.py is registered BEFORE save.py so states take priority
- handle_keyboard_button clears ALL pending states when user presses a keyboard button
- Always delete_state after processing (even on error paths)
"""

from __future__ import annotations

from aiogram import F, Router, types

from savebot.db import queries
from savebot.db.state_store import get_state, set_state, delete_state

router = Router()


# ── Step 1: Callback handler sets state and prompts ──────

@router.callback_query(F.data.startswith("va:tags:"))
async def on_action_tags(callback: types.CallbackQuery, db=None):
    item_id = int(callback.data.split(":")[2])
    user_id = callback.from_user.id

    # Set state with relevant context data
    await set_state(db, f"edit_tags_{user_id}", user_id, "edit_tags", {"item_id": item_id})

    # Show prompt to user
    await callback.message.edit_text("Введите новые теги через пробел:", parse_mode="HTML")
    await callback.answer()


# ── Step 2: state_dispatcher handles the response ────────
# In menu.py state_dispatcher (checked in order, before SkipHandler):

async def _example_state_check(message, db, user_id, text):
    """This runs inside state_dispatcher."""
    state = await get_state(db, f"edit_tags_{user_id}")
    if state:
        await delete_state(db, f"edit_tags_{user_id}")
        item_id = state["item_id"]
        # ... process the text input ...
        await message.reply("Done!")
        return True  # Handled
    return False  # Not this state


# ── Step 3: Stale state cleanup in handle_keyboard_button ─
# At the top of handle_keyboard_button, clear ALL known state prefixes:

STATE_PREFIXES = ("search_prompt_", "rename_cat_", "new_browse_cat_", "awaiting_", "edit_tags_")


async def _cleanup_stale_states(db, user_id):
    """Clear all pending states for a user. Called when keyboard button pressed."""
    for prefix in STATE_PREFIXES:
        await delete_state(db, f"{prefix}{user_id}")
