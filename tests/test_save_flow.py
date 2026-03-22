"""Tests for save flow helpers (_category_buttons, _post_save_keyboard, media group dedup)."""

import pytest
from savebot.handlers.save import (
    _category_buttons, _post_save_keyboard,
    _is_duplicate_media_group, _seen_media_groups,
)


# ── _category_buttons ─────────────────────────────────────


class TestCategoryButtons:
    def test_category_buttons_renders_7(self):
        """7 categories should produce 3 rows of 3 + 1 row of 1 (grid layout)."""
        cats = [
            {"id": i, "name": f"Cat{i}", "emoji": "📁"}
            for i in range(1, 8)
        ]
        rows = _category_buttons(cats, item_id=42)
        # 7 cats at 3 per row = 3 full rows (3+3+1)
        assert len(rows) == 3
        assert len(rows[0]) == 3
        assert len(rows[1]) == 3
        assert len(rows[2]) == 1

    def test_category_buttons_highlight(self):
        """Passing highlight_id should mark that button with a checkmark."""
        cats = [
            {"id": 1, "name": "Work", "emoji": "💼"},
            {"id": 2, "name": "Fun", "emoji": "🎮"},
        ]
        rows = _category_buttons(cats, item_id=10, highlight_id=2)
        # Flatten all buttons
        all_buttons = [btn for row in rows for btn in row]
        highlighted = [btn for btn in all_buttons if "✅" in btn.text]
        assert len(highlighted) == 1
        assert "Fun" in highlighted[0].text
        # Non-highlighted should not have checkmark
        non_highlighted = [btn for btn in all_buttons if "✅" not in btn.text]
        assert len(non_highlighted) == 1
        assert "Work" in non_highlighted[0].text


# ── _post_save_keyboard ──────────────────────────────────


class TestPostSaveKeyboard:
    def test_post_save_keyboard_has_pin_delete(self):
        """Post-save keyboard should have Pin and Delete buttons."""
        cats = [
            {"id": 1, "name": "Work", "emoji": "💼"},
            {"id": 2, "name": "Fun", "emoji": "🎮"},
        ]
        markup = _post_save_keyboard(cats, item_id=42, saved_cat_id=1)
        all_buttons = [btn for row in markup.inline_keyboard for btn in row]
        texts = [btn.text for btn in all_buttons]
        # Should have Pin button
        assert any("Pin" in t for t in texts), "Post-save keyboard should have Pin button"
        # Should have Delete button
        assert any("Удалить" in t for t in texts), "Post-save keyboard should have Delete button"


# ── Media group deduplication ─────────────────────────────


class TestMediaGroupDedup:
    def setup_method(self):
        """Clear state between tests."""
        _seen_media_groups.clear()

    def test_none_media_group_id_not_duplicate(self):
        """None media_group_id (regular message) should never be a duplicate."""
        assert _is_duplicate_media_group(None) is False
        assert _is_duplicate_media_group(None) is False

    def test_first_message_in_group_passes(self):
        """First message with a media_group_id should pass through."""
        assert _is_duplicate_media_group("group_123") is False

    def test_second_message_in_group_blocked(self):
        """Second+ messages with the same media_group_id should be blocked."""
        assert _is_duplicate_media_group("group_456") is False
        assert _is_duplicate_media_group("group_456") is True
        assert _is_duplicate_media_group("group_456") is True

    def test_different_groups_independent(self):
        """Different media_group_ids should be tracked independently."""
        assert _is_duplicate_media_group("group_A") is False
        assert _is_duplicate_media_group("group_B") is False
        assert _is_duplicate_media_group("group_A") is True
        assert _is_duplicate_media_group("group_B") is True
