"""AI categorization service using OpenRouter API."""

from __future__ import annotations

import asyncio
import json
import logging

import aiohttp

from savebot.config import config

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
Pick the BEST matching category from the list below. Respond with ONLY valid JSON, no markdown.

You MUST choose one from this list. Do NOT create new categories.
If nothing fits well, use "Разное".

Rules:
1. Tags: 1-3, lowercase, underscores (e.g. "machine_learning"). Match existing tags when possible.
2. Summary: one sentence, same language as content. Capture the KEY idea, not just the topic.
3. Emoji: pick ONE emoji that represents the category topic, not the content mood.
4. URL/link → categorize by what the link is about.
5. Forwarded message → categorize by message topic, ignore who sent it.
6. Very short content (< 10 words) → still categorize by topic. Use tags to add context.

JSON format:
{"category": "Name", "emoji": "🔬", "tags": ["tag1", "tag2"], "summary": "Краткое описание"}

Example 1:
Input: "Статья про то, как нейросети помогают в диагностике рака"
Categories: 💻 Технологии, 💰 Финансы, 🏋️ Здоровье, 📚 Обучение, 🏢 Работа, 🎨 Творчество, 📥 Разное
Output: {"category": "Технологии", "emoji": "💻", "tags": ["нейросети", "диагностика", "медицина"], "summary": "Применение нейросетей в диагностике рака"}

Example 2:
Input: "https://blog.example.com/how-to-invest-in-etf-2026"
Categories: 💻 Технологии, 💰 Финансы, 🏋️ Здоровье, 📚 Обучение, 🏢 Работа, 🎨 Творчество, 📥 Разное
Output: {"category": "Финансы", "emoji": "💰", "tags": ["etf", "инвестиции"], "summary": "Руководство по инвестированию в ETF на 2026 год"}

Example 3:
Input: "Рецепт шарлотки с яблоками"
Categories: 💻 Технологии, 💰 Финансы, 🏋️ Здоровье, 📚 Обучение, 🏢 Работа, 🎨 Творчество, 📥 Разное
Output: {"category": "Разное", "emoji": "📥", "tags": ["выпечка", "рецепт"], "summary": "Рецепт яблочной шарлотки"}
"""

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


async def classify_content(
    content_text: str,
    existing_categories: list[dict],
    existing_tags: list[str],
) -> dict | None:
    """Classify content using OpenRouter API."""
    if not config.openrouter_api_key:
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

    headers = {
        "Authorization": f"Bearer {config.openrouter_api_key}",
        "Content-Type": "application/json",
    }

    # Merge system prompt into user message for compatibility with models
    # that don't support the "system" role (e.g. gemma-3-27b-it)
    full_prompt = f"{SYSTEM_PROMPT}\n\n{user_prompt}"

    payload = {
        "model": config.ai_model,
        "messages": [
            {"role": "user", "content": full_prompt},
        ],
        "temperature": 0.3,
        "max_tokens": 300,
    }

    models_to_try = config.ai_fallback_models or [config.ai_model]

    for model in models_to_try:
        payload["model"] = model
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    OPENROUTER_URL,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    if resp.status == 429:
                        logger.warning("Model %s rate-limited (429), trying next", model)
                        await asyncio.sleep(1)
                        continue
                    if resp.status == 400:
                        logger.warning("Model %s returned 400, trying next: %s", model, await resp.text())
                        continue
                    if resp.status != 200:
                        logger.error("OpenRouter API error: %s %s", resp.status, await resp.text())
                        return None
                    data = await resp.json()

            text = data["choices"][0]["message"]["content"]
            # Strip markdown code blocks if present
            text = text.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

            result = json.loads(text)
            return {
                "category": result.get("category", "Разное"),
                "emoji": result.get("emoji", "📁"),
                "tags": [t.replace("-", "_") for t in result.get("tags", [])[:3]],
                "summary": result.get("summary", ""),
            }
        except asyncio.TimeoutError:
            logger.warning("AI classification timeout with model %s, trying next", model)
            continue
        except aiohttp.ClientError as e:
            logger.error("AI classification network error: %s", e)
            return None
        except json.JSONDecodeError as e:
            logger.error("AI classification JSON parse error: %s", e)
            return None
        except KeyError as e:
            logger.error("AI classification unexpected response structure, missing key: %s", e)
            return None
    return None
