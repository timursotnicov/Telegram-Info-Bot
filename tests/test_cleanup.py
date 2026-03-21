"""Tests for AI category cleanup."""
import pytest
from savebot.services.ai_cleanup import CLEANUP_PROMPT


class TestCleanupPrompt:
    def test_prompt_mentions_defaults(self):
        assert "Технологии" in CLEANUP_PROMPT
        assert "Разное" in CLEANUP_PROMPT

    def test_prompt_requires_json(self):
        assert "JSON" in CLEANUP_PROMPT
