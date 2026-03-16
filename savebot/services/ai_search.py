"""AI-powered search: query parsing and answer synthesis."""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta

import aiohttp

from savebot.config import config

logger = logging.getLogger(__name__)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

PARSE_QUERY_PROMPT = """\
Parse a search query into structured JSON filters. Today: {today}. Respond with ONLY valid JSON.

Format: {{"keywords": ["word1"], "date_from": "YYYY-MM-DD or null", "date_to": "YYYY-MM-DD or null", "category_hint": "or null", "tag_hint": "or null"}}

Rules:
- keywords: 1-4 main search terms, keep original language.
- date_from/date_to: only if time is mentioned. null otherwise.
  - "за последнюю неделю" / "last week" = 7 days ago → today
  - "вчера" / "yesterday" = yesterday → yesterday
  - "в январе" / "in January" = Jan 1 → Jan 31 (current year)
  - "за последний месяц" = 30 days ago → today
- category_hint/tag_hint: only if explicitly mentioned. null otherwise.
- When unsure, use null. Wrong filters are worse than missing filters.

Example: "статьи про нейросети за последнюю неделю"
Output: {{"keywords": ["нейросети", "статьи"], "date_from": "{example_week_ago}", "date_to": "{today}", "category_hint": null, "tag_hint": null}}
"""

SYNTHESIZE_PROMPT = """\
Answer the user's question using ONLY the saved items provided below. Do NOT invent information.

Rules:
1. Reference items by ID: (см. #42, #17) or (see #42, #17).
2. When referencing an item, include a brief quote from it in the format: > quote (см. #42)
3. If items don't have enough info — say so honestly, don't guess.
4. Keep answer concise: 3-5 sentences.
5. Answer in the SAME language as the user's question (usually Russian).
"""


async def _call_openrouter(system_prompt: str, user_prompt: str, temperature: float = 0.3, max_tokens: int = 300) -> str | None:
    """Shared OpenRouter API call with retry logic."""
    if not config.openrouter_api_key:
        return None

    headers = {
        "Authorization": f"Bearer {config.openrouter_api_key}",
        "Content-Type": "application/json",
    }
    # Merge system prompt into user message for compatibility with models
    # that don't support the "system" role (e.g. gemma-3-27b-it)
    full_prompt = f"{system_prompt}\n\n{user_prompt}"

    payload = {
        "model": config.ai_model,
        "messages": [
            {"role": "user", "content": full_prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
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
                    if resp.status != 200:
                        logger.error("OpenRouter API error: %s", resp.status)
                        return None
                    data = await resp.json()

            text = data["choices"][0]["message"]["content"].strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            return text.strip()
        except asyncio.TimeoutError:
            logger.warning("OpenRouter timeout with model %s, trying next", model)
            continue
        except (aiohttp.ClientError, KeyError) as e:
            logger.error("OpenRouter error: %s", e)
            return None
    return None


async def parse_search_query(query: str) -> dict | None:
    """Parse a natural language search query into structured filters."""
    today = datetime.now().strftime("%Y-%m-%d")
    example_week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    system = PARSE_QUERY_PROMPT.format(today=today, example_week_ago=example_week_ago)

    text = await _call_openrouter(system, query, temperature=0.1, max_tokens=200)
    if not text:
        return None

    try:
        result = json.loads(text)
        # Normalize null strings to None
        return {
            "keywords": result.get("keywords") or [],
            "date_from": result.get("date_from") if result.get("date_from") not in (None, "null", "") else None,
            "date_to": result.get("date_to") if result.get("date_to") not in (None, "null", "") else None,
            "category_hint": result.get("category_hint") if result.get("category_hint") not in (None, "null", "") else None,
            "tag_hint": result.get("tag_hint") if result.get("tag_hint") not in (None, "null", "") else None,
        }
    except (json.JSONDecodeError, AttributeError) as e:
        logger.error("Failed to parse search query result: %s", e)
        return None


async def synthesize_answer(question: str, items: list[dict]) -> str | None:
    """Generate an answer to user's question based on saved items."""
    if not items:
        return None

    # Build context from items
    context_parts = []
    for item in items[:15]:
        summary = item.get("ai_summary") or item.get("content_text", "")[:200]
        tags = " ".join(f"#{t}" for t in item.get("tags", []))
        date = str(item.get("created_at", ""))[:10]
        context_parts.append(f"#{item['id']}: {summary}  [{tags}] [saved: {date}]")

    user_prompt = f"Question: {question}\n\nSaved items:\n" + "\n".join(context_parts)

    return await _call_openrouter(SYNTHESIZE_PROMPT, user_prompt, temperature=0.4, max_tokens=600)
