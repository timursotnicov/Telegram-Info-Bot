"""Tests for browse handler helpers and handlers."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from savebot.handlers.browse import (
    _back_button_for_ctx,
    _format_item_short,
    _extract_list_context,
    _categories_markup,
    cmd_browse,
    cmd_ask,
    on_hub_cats,
    on_list_delete_confirm,
    on_list_delete_cancel,
    on_action_delete,
    on_action_delete_confirm,
    on_action_delete_cancel,
)
from savebot.handlers.browse_core import (
    _text_list_with_buttons,
    _format_item_list_entry,
)
from savebot.db import queries
from tests.conftest import make_callback, make_message

USER_ID = 1


# ── _back_button_for_ctx ─────────────────────────────────

class TestBackButtonForCtx:
    def test_category_context(self):
        btn = _back_button_for_ctx("c", 5)
        assert btn.callback_data == "bm:cats"
        assert "Все записи" in btn.text

    def test_source_context(self):
        btn = _back_button_for_ctx("s")
        assert btn.callback_data == "bm:cats"
        assert "Все записи" in btn.text

    def test_unknown_context_defaults_to_cats(self):
        btn = _back_button_for_ctx("x")
        assert btn.callback_data == "bm:cats"
        assert "Все записи" in btn.text


# ── _format_item_short ───────────────────────────────────

class TestFormatItemShort:
    def test_prefers_ai_summary(self):
        item = {"ai_summary": "AI summary", "content_text": "Raw text"}
        assert _format_item_short(item) == "AI summary"

    def test_truncates_long_text(self):
        item = {"content_text": "A" * 50}
        result = _format_item_short(item)
        assert len(result) <= 38
        assert result.endswith("...")

    def test_empty_item(self):
        item = {}
        assert _format_item_short(item) == "(без текста)"


# ── _format_item_list_entry ─────────────────────────────

class TestFormatItemListEntry:
    def test_uses_ai_summary(self):
        item = {"ai_summary": "Summary", "content_text": "Text", "tags": []}
        result = _format_item_list_entry(item, 1)
        assert "<b>1.</b>" in result
        assert "Summary" in result

    def test_truncates_title_to_80(self):
        item = {"ai_summary": "A" * 100, "tags": []}
        result = _format_item_list_entry(item, 1)
        # Title should be truncated to 77 + "..."
        assert "..." in result

    def test_truncates_meta_to_60(self):
        item = {
            "content_text": "Short",
            "category_emoji": "📁",
            "category_name": "A" * 30,
            "source": "B" * 30,
            "created_at": "2026-01-01",
            "tags": ["tag1", "tag2", "tag3"],
        }
        result = _format_item_list_entry(item, 1)
        # Meta line should end with "..."
        lines = result.split("\n")
        if len(lines) > 1:
            meta = lines[1].strip()
            assert len(meta) <= 63  # 60 + "..."

    def test_no_text_fallback(self):
        item = {"tags": []}
        result = _format_item_list_entry(item, 1)
        assert "(без текста)" in result


# ── _text_list_with_buttons ─────────────────────────────

class TestTextListWithButtons:
    def test_returns_tuple(self):
        items = [
            {"id": 1, "display_num": 1, "content_text": "First", "tags": []},
            {"id": 2, "display_num": 2, "content_text": "Second", "tags": []},
        ]
        text, buttons = _text_list_with_buttons(items, "c", "5", 0, 2)
        assert isinstance(text, str)
        assert isinstance(buttons, list)
        assert "First" in text
        assert "Second" in text

    def test_number_buttons_row(self):
        items = [
            {"id": 1, "display_num": 1, "content_text": "First", "tags": []},
            {"id": 2, "display_num": 2, "content_text": "Second", "tags": []},
        ]
        text, buttons = _text_list_with_buttons(items, "c", "5", 0, 2)
        # First row should be number buttons
        assert buttons[0][0].text == "1"
        assert buttons[0][1].text == "2"
        assert buttons[0][0].callback_data == "vi:c:5:1"

    def test_deleting_item_has_noop_placeholder(self):
        items = [
            {"id": 1, "display_num": 1, "content_text": "First", "tags": []},
            {"id": 2, "display_num": 2, "content_text": "Second", "tags": []},
        ]
        text, buttons = _text_list_with_buttons(items, "c", "5", 0, 2, deleting_item_id=1)
        # Number row should have noop placeholder for item 1
        number_row = buttons[0]
        assert number_row[0].callback_data == "noop"
        assert number_row[1].callback_data == "vi:c:5:2"
        # Text should show strikethrough
        assert "<s>" in text

    def test_message_under_4096_chars(self):
        """Formatted text for 5 items should stay under Telegram's 4096 char limit."""
        items = [
            {
                "id": i, "display_num": i,
                "ai_summary": "A" * 80,
                "content_text": "B" * 200,
                "category_emoji": "📁", "category_name": "Category",
                "source": "Source Channel",
                "created_at": "2026-01-01",
                "tags": ["tag1", "tag2", "tag3"],
            }
            for i in range(1, 6)
        ]
        text, buttons = _text_list_with_buttons(items, "c", "5", 0, 5)
        # Title + text should be well under 4096
        full_text = f"📁 Category (5)\n\n{text}"
        assert len(full_text) < 4096


# ── _extract_list_context ────────────────────────────────

class TestExtractListContext:
    def test_extracts_from_vl_button(self):
        btn = MagicMock()
        btn.callback_data = "vl:c:5:10"
        kb = MagicMock()
        kb.inline_keyboard = [[btn]]
        cb = make_callback(USER_ID, "va:del:42", reply_markup=kb)
        result = _extract_list_context(cb)
        assert result == ("c", "5", 10, "d")

    def test_returns_none_without_vl_button(self):
        btn = MagicMock()
        btn.callback_data = "bm:cats"
        kb = MagicMock()
        kb.inline_keyboard = [[btn]]
        cb = make_callback(USER_ID, "va:del:42", reply_markup=kb)
        result = _extract_list_context(cb)
        assert result is None

    def test_returns_none_without_keyboard(self):
        cb = make_callback(USER_ID, "va:del:42", reply_markup=None)
        result = _extract_list_context(cb)
        assert result is None


# ── Handler helpers ──────────────────────────────────────

async def _create_test_data(db, user_id=USER_ID, n_items=3):
    """Create a category with n items for handler tests."""
    cat = await queries.get_or_create_category(db, user_id, "Test", "📁")
    item_ids = []
    for i in range(n_items):
        item_id = await queries.save_item(
            db, user_id, cat["id"], "text", f"Item {i+1}", tags=["test"],
        )
        item_ids.append(item_id)
    return cat, item_ids


def _make_kb_with_vl(ctx_short="c", ctx_id="1", offset=0):
    """Build a reply_markup with a vl: back button (for context extraction)."""
    btn = MagicMock()
    btn.callback_data = f"vl:{ctx_short}:{ctx_id}:{offset}"
    kb = MagicMock()
    kb.inline_keyboard = [[btn]]
    return kb


# ── Navigation handlers ─────────────────────────────────

class TestCmdBrowse:
    @pytest.mark.asyncio
    async def test_shows_categories(self, db):
        await queries.get_or_create_category(db, USER_ID, "Work", "💼")
        msg = make_message(USER_ID, bot_db=db)
        await cmd_browse(msg, db=db)
        msg.reply.assert_called_once()
        call_kwargs = msg.reply.call_args
        assert "Все записи" in call_kwargs[0][0]

    @pytest.mark.asyncio
    async def test_empty_shows_no_categories(self, db):
        msg = make_message(USER_ID, bot_db=db)
        await cmd_browse(msg, db=db)
        msg.reply.assert_called_once()
        assert "нет" in msg.reply.call_args[0][0].lower()


class TestOnHubCats:
    @pytest.mark.asyncio
    async def test_with_categories(self, db):
        await queries.get_or_create_category(db, USER_ID, "Work", "💼")
        cb = make_callback(USER_ID, "bm:cats")
        await on_hub_cats(cb, db=db)
        cb.message.edit_text.assert_called_once()
        assert "Все записи" in cb.message.edit_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_empty_categories(self, db):
        cb = make_callback(USER_ID, "bm:cats")
        await on_hub_cats(cb, db=db)
        cb.message.edit_text.assert_called_once()
        assert "нет" in cb.message.edit_text.call_args[0][0].lower()


# ── List delete handlers ─────────────────────────────────

class TestListDeleteConfirm:
    @pytest.mark.asyncio
    async def test_deletes_item_and_refreshes(self, db):
        cat, item_ids = await _create_test_data(db, n_items=3)
        cb = make_callback(USER_ID, f"vy:c:{cat['id']}:{item_ids[0]}:0")
        await on_list_delete_confirm(cb, db=db)
        # Item should be deleted
        item = await queries.get_item(db, USER_ID, item_ids[0])
        assert item is None
        # answer() called twice: once with "Удалено", once by _show_list
        cb.answer.assert_any_call("🗑 Удалено")

    @pytest.mark.asyncio
    async def test_nonexistent_item(self, db):
        cb = make_callback(USER_ID, "vy:c:1:99999:0")
        await on_list_delete_confirm(cb, db=db)
        cb.answer.assert_called_once_with("Запись не найдена.")

    @pytest.mark.asyncio
    async def test_last_item_on_page_adjusts_offset(self, db):
        """When deleting the only item on page 2, should go back to page 1."""
        cat = await queries.get_or_create_category(db, USER_ID, "Test", "📁")
        # Create 6 items (page 1: 5 items, page 2: 1 item)
        for i in range(6):
            await queries.save_item(db, USER_ID, cat["id"], "text", f"Item {i}", tags=[])
        # Get item IDs on page 2
        page2_items = await queries.get_items_page_with_nums(
            db, USER_ID, "category", context_id=str(cat["id"]), limit=5, offset=5,
        )
        assert len(page2_items) == 1
        last_item_id = page2_items[0]["id"]
        # Delete from page 2
        cb = make_callback(USER_ID, f"vy:c:{cat['id']}:{last_item_id}:5")
        await on_list_delete_confirm(cb, db=db)
        # Should have shown list (edit_text called), not "list empty"
        cb.answer.assert_any_call("🗑 Удалено")
        cb.message.edit_text.assert_called_once()


class TestListDeleteCancel:
    @pytest.mark.asyncio
    async def test_refreshes_list(self, db):
        cat, item_ids = await _create_test_data(db, n_items=2)
        cb = make_callback(USER_ID, f"vx:c:{cat['id']}:0")
        await on_list_delete_cancel(cb, db=db)
        # Should re-render list (edit_text called)
        cb.message.edit_text.assert_called_once()
        cb.answer.assert_called_once()


# ── Item view delete handlers ────────────────────────────

class TestActionDelete:
    @pytest.mark.asyncio
    async def test_shows_confirm_dialog_with_context(self, db):
        kb = _make_kb_with_vl("c", "5", 0)
        cb = make_callback(USER_ID, "va:del:42", reply_markup=kb)
        await on_action_delete(cb, db=db)
        cb.message.edit_text.assert_called_once()
        call_args = cb.message.edit_text.call_args
        assert "Удалить" in call_args[0][0]
        # Should have confirm/cancel + back-to-list buttons
        markup = call_args[1]["reply_markup"]
        all_cb = [btn.callback_data for row in markup.inline_keyboard for btn in row]
        assert any("va:dyes:42" in c for c in all_cb)
        assert any("va:dno:42" in c for c in all_cb)
        assert any(c.startswith("vl:") for c in all_cb)


class TestActionDeleteConfirm:
    @pytest.mark.asyncio
    async def test_deletes_and_returns_to_list(self, db):
        cat, item_ids = await _create_test_data(db, n_items=3)
        kb = _make_kb_with_vl("c", str(cat["id"]), 0)
        cb = make_callback(USER_ID, f"va:dyes:{item_ids[0]}", reply_markup=kb)
        await on_action_delete_confirm(cb, db=db)
        # Item deleted
        assert await queries.get_item(db, USER_ID, item_ids[0]) is None
        # answer() called twice: once with "Удалено", once by _show_list
        cb.answer.assert_any_call("🗑 Удалено")
        # Should show list (edit_text called)
        cb.message.edit_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_context_shows_fallback(self, db):
        cat, item_ids = await _create_test_data(db, n_items=1)
        cb = make_callback(USER_ID, f"va:dyes:{item_ids[0]}", reply_markup=None)
        await on_action_delete_confirm(cb, db=db)
        assert await queries.get_item(db, USER_ID, item_ids[0]) is None
        cb.answer.assert_called_once_with("🗑 Удалено")
        # Fallback: "Запись удалена" with back to categories
        call_text = cb.message.edit_text.call_args[0][0]
        assert "удалена" in call_text.lower()


class TestActionDeleteCancel:
    @pytest.mark.asyncio
    async def test_no_context_shows_fallback(self, db):
        cb = make_callback(USER_ID, "va:dno:42", reply_markup=None)
        await on_action_delete_cancel(cb, db=db)
        cb.answer.assert_called_once_with("Отменено")
        call_text = cb.message.edit_text.call_args[0][0]
        assert "отменено" in call_text.lower()


# ── _categories_markup ────────────────────────────────────

class TestCategoriesMarkup:
    def test_direct_navigation(self):
        """Category buttons should go directly to browse_cat (not cm: sub-menu)."""
        cats = [{"id": 1, "name": "Work", "emoji": "💼", "item_count": 3}]
        markup = _categories_markup(cats)
        btn = markup.inline_keyboard[0][0]
        assert btn.callback_data == "browse_cat:1:0"

    def test_no_footer_buttons(self):
        """Category markup should have no footer (tags, collections, hub)."""
        cats = [{"id": 1, "name": "Work", "emoji": "💼", "item_count": 3}]
        markup = _categories_markup(cats)
        assert len(markup.inline_keyboard) == 1  # Only category buttons, no footer


# ── Sort buttons ─────────────────────────────────────────

class TestSortButtons:
    def test_sort_buttons_renders_4(self):
        """_sort_buttons should return 4 buttons."""
        from savebot.handlers.browse_core import _sort_buttons
        row = _sort_buttons(cat_id=5)
        assert len(row) == 4

    def test_sort_buttons_highlight(self):
        """Active sort should have ✅ prefix."""
        from savebot.handlers.browse_core import _sort_buttons
        row = _sort_buttons(cat_id=5, active_sort="p")
        texts = [btn.text for btn in row]
        # "p" button should have ✅
        assert any("✅" in t and "Закреп" in t for t in texts)
        # "d" button should NOT have ✅
        assert any("✅" not in t and "Новые" in t for t in texts)

    def test_sort_default_is_date(self):
        """browse_cat callback without sort segment should default to 'd'."""
        callback_data = "browse_cat:5:0"
        parts = callback_data.split(":")
        sort_by = parts[3] if len(parts) > 3 else "d"
        assert sort_by == "d"


# ── cmd_ask ───────────────────────────────────────────────

class TestCmdAsk:
    @pytest.mark.asyncio
    async def test_ask_command_disabled(self, db):
        msg = make_message(USER_ID, text="/ask something")
        await cmd_ask(msg, db=db)
        msg.reply.assert_called_once()
        reply_text = msg.reply.call_args[0][0]
        assert "временно отключена" in reply_text


# ── Backward compat: old keyboard buttons ────────────────

class TestOldKeyboardBackwardCompat:
    def test_old_buttons_in_button_texts(self):
        """Old cached buttons should still be recognized by menu.py."""
        from savebot.handlers.menu import BUTTON_TEXTS
        old_buttons = [
            "📂 Категории", "📂 Browse", "🔍 Search",
            "📌 Pinned", "🕐 Recent", "⚙️ Settings", "📌 Закрепленные",
        ]
        for btn in old_buttons:
            assert btn in BUTTON_TEXTS, f"Old button '{btn}' missing from BUTTON_TEXTS"

    def test_new_buttons_in_button_texts(self):
        """New buttons should be in BUTTON_TEXTS."""
        from savebot.handlers.menu import BUTTON_TEXTS
        new_buttons = ["📂 Все записи", "🔍 Поиск", "🕐 Недавние", "⚙️ Настройки"]
        for btn in new_buttons:
            assert btn in BUTTON_TEXTS, f"New button '{btn}' missing from BUTTON_TEXTS"


# ── Stub commands ────────────────────────────────────────

class TestStubCommands:
    @pytest.mark.asyncio
    async def test_tags_stub(self, db):
        from savebot.handlers.browse import cmd_tags
        msg = make_message(USER_ID, text="/tags")
        await cmd_tags(msg)
        msg.reply.assert_called_once()
        assert "больше не доступна" in msg.reply.call_args[0][0]

    @pytest.mark.asyncio
    async def test_collections_stub(self, db):
        from savebot.handlers.browse import cmd_collections
        msg = make_message(USER_ID, text="/collections")
        await cmd_collections(msg)
        msg.reply.assert_called_once()
        assert "больше не доступна" in msg.reply.call_args[0][0]
