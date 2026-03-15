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
You are a search query parser. The user will give you a search query in any language.
Extract structured filters from it. Today's date is {today}.

Respond with ONLY valid JSON (no markdown, no code blocks):
{{"keywords": ["word1", "word2"], "date_from": "YYYY-MM-DD or null", "date_to": "YYYY-MM-DD or null", "category_hint": "category name or null", "tag_hint": "tag name or null"}}

Rules:
- keywords: the main search terms, 1-4 words. Keep in original language.
- date_from / date_to: only if the query mentions time ("last week" = 7 days ago, "yesterday" = yesterday, "in January" = Jan 1 to Jan 31). Use null if no time mentioned.
- category_hint: only if the query explicitly mentions a category name. Use null otherwise.
- tag_hint: only if the query explicitly mentions a tag. Use null otherwise.
- If unsure about a filter, use null. Fewer wrong filters is better than more wrong filters.
"""

SYNTHESIZE_PROMPT = """\
You are a helpful assistant. The user has a personal knowledge base of saved items.
You will receive the user's question and a list of their saved items that might be relevant.

Your task:
1. Answer the question based ONLY on the provided items. Do not invent information.
2. Reference items by their ID numbers like this: (see #42, #17).
3. If the items don't contain enough info to answer, say so honestly.
4. Keep your answer concise (3-5 sentences).
5. Answer in the same language the user used in their question.
"""


async def _call_openrouter(system_prompt: str, user_prompt: str, temperature: float = 0.3, max_tokens: int = 300) -> str | None:
    """Shared OpenRouter API call with retry logic."""
    if not config.openrouter_api_key:
        return None

    headers = {
        "Authorization": f"Bearer {config.openrouter_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": config.ai_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    for attempt in range(2):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    OPENROUTER_URL,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
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
            logger.warning("OpenRouter timeout (attempt %d/2)", attempt + 1)
            if attempt == 0:
                await asyncio.sleep(2)
                continue
            return None
        except (aiohttp.ClientError, KeyError) as e:
            logger.error("OpenRouter error: %s", e)
            return None
    return None


async def parse_search_query(query: str) -> dict | None:
    """Parse a natural language search query into structured filters."""
    today = datetime.now().strftime("%Y-%m-%d")
    system = PARSE_QUERY_PROMPT.format(today=today)

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
