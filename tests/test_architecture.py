"""Structural tests: router order and callback data limits."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

BOT_PY = Path(__file__).resolve().parent.parent / "savebot" / "bot.py"

EXPECTED_ROUTER_ORDER = ["settings", "manage", "menu", "browse", "inline", "save"]

ROUTER_ORDER_ERROR = (
    "Router order MUST be: settings \u2192 manage \u2192 menu \u2192 browse \u2192 inline \u2192 save. "
    "menu before browse (state dispatcher). save last (catch-all). "
    "See docs/decisions/002-router-order.md"
)

CALLBACK_PATTERNS = [
    "vi:c:99999:99999",
    "vd:t:12345678901234567890:99999:99999",
    "vy:t:12345678901234567890:99999:99999",
    "vx:t:12345678901234567890:99999",
    "va:dyes:99999",
    "browse_cat:99999:99999:d",
    "tag_items:12345678901234567890:99999",
    "vl:t:12345678901234567890:99999:d",
    "settings_toggle:daily_brief_enabled",
    "settings_brief_time:23:59",
    "autosave_pick:99999:99999",
]


class TestRouterOrder:
    """Verify that routers are registered in the correct order in bot.py."""

    def test_router_order_matches_expected(self):
        source = BOT_PY.read_text(encoding="utf-8")
        matches = re.findall(r"dp\.include_router\((\w+)\.router\)", source)
        assert matches == EXPECTED_ROUTER_ORDER, ROUTER_ORDER_ERROR


class TestBotSourceChecks:
    """Verify source-level constraints on bot.py and handler files."""

    def test_bot_commands_no_ask(self):
        source = BOT_PY.read_text(encoding="utf-8")
        # The commands list in set_bot_commands should not include "ask"
        import ast
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.List):
                for elt in node.elts:
                    if isinstance(elt, ast.Call):
                        for kw in elt.keywords:
                            if kw.arg == "command":
                                if isinstance(kw.value, ast.Constant):
                                    assert kw.value.value != "ask", (
                                        "/ask should not be in bot commands list"
                                    )

    def test_menu_no_forcereply(self):
        menu_py = BOT_PY.parent / "handlers" / "menu.py"
        source = menu_py.read_text(encoding="utf-8")
        assert "ForceReply" not in source, (
            "menu.py should not use ForceReply — use state_store pattern instead"
        )


class TestCallbackDataLimit:
    """Verify that the longest possible callback_data for each pattern fits in 64 bytes."""

    @pytest.mark.parametrize("pattern", CALLBACK_PATTERNS)
    def test_callback_pattern_within_64_bytes(self, pattern: str):
        length = len(pattern.encode("utf-8"))
        assert length <= 64, (
            f"Callback data '{pattern}' is {length} bytes, exceeds 64 byte "
            "Telegram limit. See docs/decisions/003-callback-data-limit.md"
        )
