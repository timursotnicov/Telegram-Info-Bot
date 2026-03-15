"""AI categorization service using Google Gemini Flash API."""

from __future__ import annotations

import json
import logging

import aiohttp

from savebot.config import config

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a content categorization assistant. Given a piece of content, you must categorize it.

You will receive:
- The content text
- A list of existing categories (use one if appropriate)
- A list of frequently used tags

Rules:
1. Pick the BEST existing category, or suggest a new one if none fit.
2. Suggest 1-3 relevant tags (short, lowercase, no #).
3. Write a one-sentence summary in the same language as the content.
4. For the category, also suggest an appropriate emoji.

Respond with ONLY valid JSON (no markdown, no code blocks):
{"category": "CategoryName", "emoji": "📁", "tags": ["tag1", "tag2"], "summary": "Brief summary"}
"""


async def classify_content(
    content_text: str,
    existing_categories: list[dict],
    existing_tags: list[str],
) -> dict | None:
    """Classify content using Gemini Flash API. Returns dict with category, emoji, tags, summary."""
    if not config.gemini_api_key:
        return None

    categories_str = ", ".join(
        f"{c.get('emoji', '📁')} {c['name']}" for c in existing_categories
    ) or "No categories yet"

    tags_str = ", ".join(existing_tags[:20]) or "No tags yet"

    user_prompt = (
        f"Content:\n{content_text[:2000]}\n\n"
        f"Existing categories: {categories_str}\n"
        f"Frequently used tags: {tags_str}"
    )

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={config.gemini_api_key}"

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": f"{SYSTEM_PROMPT}\n\n{user_prompt}"}
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.3,
            "maxOutputTokens": 300,
        },
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    logger.error("Gemini API error: %s %s", resp.status, await resp.text())
                    return None
                data = await resp.json()

        text = data["candidates"][0]["content"]["parts"][0]["text"]
        # Strip markdown code blocks if present
        text = text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        result = json.loads(text)
        return {
            "category": result.get("category", "Inbox"),
            "emoji": result.get("emoji", "📁"),
            "tags": result.get("tags", [])[:3],
            "summary": result.get("summary", ""),
        }
    except Exception as e:
        logger.error("AI classification failed: %s", e)
        return None
