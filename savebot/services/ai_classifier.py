"""AI categorization service using OpenRouter API."""

from __future__ import annotations

import asyncio
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
1. Pick the BEST existing category, or suggest a NEW descriptive one if none fit well.
2. NEVER use generic names like "Inbox", "Other", "General", "Misc". Always pick a specific topic name.
3. Предпочитай КОНКРЕТНЫЕ подкатегории вместо общих. Примеры:
   - НЕ «Технологии» → а «Искусственный интеллект», «Веб-разработка», «Кибербезопасность»
   - НЕ «Бизнес» → а «Маркетинг», «Стартапы», «Финансы», «Продажи»
   - НЕ «Наука» → а «Космос», «Биология», «Физика»
   - НЕ «Образование» → а «Программирование», «Языки», «Саморазвитие»
4. Используй существующую категорию ТОЛЬКО если контент точно попадает в её тематику. Если нет — создай новую более конкретную.
5. Длина названия категории: 1-3 слова. Не длиннее.
6. Suggest 1-3 relevant tags (short, lowercase, no #).
7. Write a one-sentence summary in the same language as the content.
8. For the category, also suggest an appropriate emoji.

Respond with ONLY valid JSON (no markdown, no code blocks):
{"category": "CategoryName", "emoji": "📁", "tags": ["tag1", "tag2"], "summary": "Brief summary"}
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
                "category": result.get("category", "Inbox"),
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
