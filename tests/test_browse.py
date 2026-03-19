"""Tests for browse handler helpers and handlers."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from savebot.handlers.browse import (
    _back_button_for_ctx,
    _format_item_short,
    _clickable_list_buttons,
    _extract_list_context,
    _more_markup,
    _categories_markup,
    cmd_browse,
    cmd_ask,
    on_hub,
    on_hub_cats,
    on_list_delete_confirm,
    on_list_delete_cancel,
    on_action_delete,
    on_action_delete_confirm,
    on_action_delete_cancel,
)
from savebot.db import queries
from tests.conftest import make_callback, make_message

USER_ID = 1


# ── _back_button_for_ctx ─────────────────────────────────

class TestBackButtonForCtx:
    def test_category_context(self):
        btn = _back_button_for_ctx("c")
        assert btn.callback_data == "bm:cats"
        assert "категориям" in btn.text.lower()

    def test_tag_context(self):
        btn = _back_button_for_ctx("t")
        assert btn.callback_data == "tags_back"
        assert "тегам" in btn.text.lower()

    def test_collection_context(self):
        btn = _back_button_for_ctx("o")
        assert btn.callback_data == "bm:colls"
        assert "коллекциям" in btn.text.lower()

    def test_unknown_context_defaults_to_categories(self):
        btn = _back_button_for_ctx("x")
        assert btn.callback_data == "bm:cats"


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


# ── _clickable_list_buttons ──────────────────────────────

class TestClickableListButtons:
    def test_normal_items_have_trash_button(self):
        items = [
            {"id": 1, "display_num": 1, "content_text": "First"},
            {"id": 2, "display_num": 2, "content_text": "Second"},
        ]
        buttons = _clickable_list_buttons(items, "c", "5", 0, 2)
        # Each item row: [item_button, trash_button]
        assert len(buttons[0]) == 2
        assert buttons[0][1].text == "🗑"
        assert buttons[0][1].callback_data.startswith("vd:")

    def test_deleting_item_shows_confirm_row(self):
        items = [
            {"id": 1, "display_num": 1, "content_text": "First"},
            {"id": 2, "display_num": 2, "content_text": "Second"},
        ]
        buttons = _clickable_list_buttons(items, "c", "5", 0, 2, deleting_item_id=1)
        # Item 1 should be confirmation row: [label, ✅, ❌]
        assert len(buttons[0]) == 3
        assert "Удалить" in buttons[0][0].text
        assert buttons[0][1].text == "✅"
        assert buttons[0][1].callback_data.startswith("vy:")
        assert buttons[0][2].text == "❌"
        assert buttons[0][2].callback_data.startswith("vx:")
        # Item 2 should be normal
        assert buttons[1][1].text == "🗑"


# ── _extract_list_context ────────────────────────────────

class TestExtractListContext:
    def test_extracts_from_vl_button(self):
        btn = MagicMock()
        btn.callback_data = "vl:c:5:10"
        kb = MagicMock()
        kb.inline_keyboard = [[btn]]
        cb = make_callback(USER_ID, "va:del:42", reply_markup=kb)
        result = _extract_list_context(cb)
        assert result == ("c", "5", 10)

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
        assert "Категории" in call_kwargs[0][0]

    @pytest.mark.asyncio
    async def test_empty_shows_no_categories(self, db):
        msg = make_message(USER_ID, bot_db=db)
        await cmd_browse(msg, db=db)
        msg.reply.assert_called_once()
        assert "нет" in msg.reply.call_args[0][0].lower()


class TestOnHub:
    @pytest.mark.asyncio
    async def test_shows_more_menu(self, db):
        cb = make_callback(USER_ID, "bm:hub")
        await on_hub(cb, db=db)
        cb.message.edit_text.assert_called_once()
        call_args = cb.message.edit_text.call_args
        assert "Ещё" in call_args[0][0]
        # Check markup has expected buttons
        markup = call_args[1]["reply_markup"]
        all_cb = [btn.callback_data for row in markup.inline_keyboard for btn in row]
        assert "bm:colls" in all_cb
        assert "bm:map" in all_cb
        assert "bm:cats" in all_cb


class TestOnHubCats:
    @pytest.mark.asyncio
    async def test_with_categories(self, db):
        await queries.get_or_create_category(db, USER_ID, "Work", "💼")
        cb = make_callback(USER_ID, "bm:cats")
        await on_hub_cats(cb, db=db)
        cb.message.edit_text.assert_called_once()
        assert "Категории" in cb.message.edit_text.call_args[0][0]

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


# ── _more_markup ──────────────────────────────────────────

class TestMoreMarkup:
    def test_more_markup_no_forgotten(self):
        markup = _more_markup()
        all_texts = [btn.text for row in markup.inline_keyboard for btn in row]
        for text in all_texts:
            assert "Забытые" not in text, "More menu should not contain 'Забытые'"

    def test_more_markup_no_channels(self):
        markup = _more_markup()
        all_texts = [btn.text for row in markup.inline_keyboard for btn in row]
        for text in all_texts:
            assert "Каналы" not in text, "More menu should not contain 'Каналы'"


# ── _categories_markup ────────────────────────────────────

class TestCategoriesMarkup:
    def test_categories_markup_no_tags(self):
        cats = [{"id": 1, "name": "Work", "emoji": "💼", "item_count": 3}]
        markup = _categories_markup(cats)
        all_texts = [btn.text for row in markup.inline_keyboard for btn in row]
        for text in all_texts:
            assert "Теги" not in text, "Category markup footer should not contain 'Теги'"


# ── cmd_ask ───────────────────────────────────────────────

class TestCmdAsk:
    @pytest.mark.asyncio
    async def test_ask_command_disabled(self, db):
        msg = make_message(USER_ID, text="/ask something")
        await cmd_ask(msg, db=db)
        msg.reply.assert_called_once()
        reply_text = msg.reply.call_args[0][0]
        assert "временно отключена" in reply_text
