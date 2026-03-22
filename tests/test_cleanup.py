"""Tests for AI category cleanup."""
import pytest
from savebot.services.ai_cleanup import CLEANUP_PROMPT, _try_fix_truncated_json


class TestCleanupPrompt:
    def test_prompt_mentions_defaults(self):
        assert "Технологии" in CLEANUP_PROMPT
        assert "Разное" in CLEANUP_PROMPT

    def test_prompt_requires_json(self):
        assert "JSON" in CLEANUP_PROMPT


class TestTryFixTruncatedJson:
    def test_fixes_truncated_array(self):
        """Should salvage complete objects from a truncated JSON array."""
        truncated = '[{"action": "keep", "category": "Work", "reason": "ok"}, {"action": "merge", "categ'
        result = _try_fix_truncated_json(truncated)
        assert result is not None
        assert len(result) == 1
        assert result[0]["action"] == "keep"

    def test_valid_json_not_needed(self):
        """Already valid JSON should not be passed here, but empty should return None."""
        assert _try_fix_truncated_json("") is None
        assert _try_fix_truncated_json(None) is None

    def test_no_objects_returns_none(self):
        """If no complete object found, return None."""
        assert _try_fix_truncated_json('[{"action": "ke') is None

    def test_not_array_returns_none(self):
        """Non-array JSON should return None."""
        assert _try_fix_truncated_json('{"action": "keep"}') is None
