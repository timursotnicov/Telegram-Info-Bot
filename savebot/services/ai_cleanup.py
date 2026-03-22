"""AI-powered category consolidation service."""
from __future__ import annotations

import json
import logging

from savebot.services.ai_classifier import _strip_code_blocks

logger = logging.getLogger(__name__)


def _try_fix_truncated_json(text: str) -> list[dict] | None:
    """Try to parse truncated JSON array by finding the last complete object."""
    if not text or not text.strip().startswith("["):
        return None
    # Find the last complete object (ends with })
    last_brace = text.rfind("}")
    if last_brace == -1:
        return None
    candidate = text[:last_brace + 1].rstrip().rstrip(",") + "]"
    try:
        result = json.loads(candidate)
        if isinstance(result, list) and len(result) > 0:
            logger.info("AI cleanup: salvaged %d suggestions from truncated JSON", len(result))
            return result
    except (json.JSONDecodeError, TypeError):
        pass
    return None


CLEANUP_PROMPT = """\
Analyze these categories and their sample items. Suggest a consolidation plan.

Rules:
1. Keep the 7 default categories: Технологии, Финансы, Здоровье, Обучение, Работа, Творчество, Разное.
2. For each non-default category, suggest ONE action:
   - "merge" into a default or larger category (with reason)
   - "keep" if it has a clear distinct purpose and enough items
   - "delete" if empty (0 items)
3. For orphan items that don't fit any category well, suggest creating a new category ONLY if 3+ items share a theme.
4. Respond with ONLY valid JSON array.

JSON format:
[
  {"category": "Name", "action": "merge", "target": "Target Category", "reason": "..."},
  {"category": "Name", "action": "keep", "reason": "..."},
  {"category": "Name", "action": "delete", "reason": "empty"},
  {"action": "create", "name": "New Category", "emoji": "🎯", "items": [id1, id2, id3], "reason": "..."}
]
"""


async def analyze_categories(db, user_id: int) -> list[dict] | None:
    """Ask AI to analyze categories and suggest a consolidation plan."""
    from savebot.db import queries
    from savebot.services.ai_search import _call_openrouter

    categories = await queries.get_all_categories(db, user_id)
    if not categories:
        return None

    # Build context: categories with sample items
    context_parts = []
    for cat in categories:
        items = await queries.get_items_by_category(
            db, user_id, cat["id"], limit=5, offset=0,
        )
        sample = []
        for item in items:
            summary = item.get("ai_summary") or (item.get("content_text", "")[:80])
            tags = ", ".join(item.get("tags", []))
            sample.append(f"  - #{item['id']}: {summary} [{tags}]")

        header = f"{cat.get('emoji', '\U0001f4c1')} {cat['name']} ({cat.get('item_count', 0)} items)"
        if sample:
            context_parts.append(header + "\n" + "\n".join(sample))
        else:
            context_parts.append(header + "\n  (empty)")

    user_prompt = "Categories and sample items:\n\n" + "\n\n".join(context_parts)

    text = await _call_openrouter(CLEANUP_PROMPT, user_prompt, temperature=0.3, max_tokens=2000)
    if not text:
        return None

    try:
        text = _strip_code_blocks(text)
        result = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        # Try to salvage truncated JSON by closing open brackets
        result = _try_fix_truncated_json(text)
        if result is None:
            logger.error("AI cleanup parse error: could not parse or fix response")
            return None

    if not isinstance(result, list):
        return None
    return result
