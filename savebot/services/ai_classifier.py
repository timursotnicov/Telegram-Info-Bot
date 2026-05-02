"""AI categorization service using OpenRouter API."""

from __future__ import annotations

import asyncio
import difflib
import json
import logging
import re
import unicodedata

import aiohttp

from savebot.config import config

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You classify saved posts for a personal knowledge base.

Return ONLY valid JSON, no markdown:
{"category":"Exact category name","emoji":"📁","tags":["tag_one"],"summary":"One short sentence"}

Category rules:
1. The "category" value MUST be one exact category name from the catalog below. Do not invent categories.
2. Choose by the real subject of the post, not by the source, domain, author, or message mood.
3. Use "Разное" only as a last resort when no listed category fits.
4. URL/link content should be categorized by title/description when provided.
5. Forwarded messages should be categorized by message topic, not by who sent them.
6. If the content is a course, lecture, guide, framework notes, or learning material, prefer "Обучение" unless the post is mainly a work task.

Tag rules:
1. 1-3 tags only.
2. lowercase, no "#", spaces as underscores.
3. Match existing tags when possible.
4. Tags describe the specific topic, not the broad category.
5. For Russian content prefer Russian tags, except common product names or English terms like API, ETF, Python, JTBD.

Summary rules:
1. One short sentence.
2. Same language as the content.
3. Capture the key idea, not only the broad topic.
"""

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

_CODE_BLOCK_RE = re.compile(r"^```\w*\n?", re.MULTILINE)
_CODE_BLOCK_END_RE = re.compile(r"\n?```$")
_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)
_NON_TAG_CHARS_RE = re.compile(r"[^\w]+", re.UNICODE)

CATEGORY_GUIDANCE = {
    "Технологии": "software, AI/LLM, programming, automation, developer tools, gadgets, IT, APIs, infrastructure",
    "Финансы": "money, investing, ETF, stocks, crypto, taxes, budgeting, banks, accounting",
    "Здоровье": "fitness, sleep, nutrition, medicine, mental health, habits, body",
    "Обучение": "courses, lectures, tutorials, books, research notes, frameworks learned for future use",
    "Работа": "tasks, meetings, clients, contracts, deadlines, hiring, operations, business execution",
    "Творчество": "design, writing, visual ideas, content creation, music, art, landing/page creative concepts",
    "Разное": "recipes, shopping, entertainment, personal trivia, or content that does not fit other categories",
}

CATEGORY_ALIASES = {
    "tech": "Технологии",
    "technology": "Технологии",
    "technologies": "Технологии",
    "ai": "Технологии",
    "ai llm": "Технологии",
    "llm": "Технологии",
    "programming": "Технологии",
    "software": "Технологии",
    "финансы": "Финансы",
    "finance": "Финансы",
    "finances": "Финансы",
    "money": "Финансы",
    "investing": "Финансы",
    "investment": "Финансы",
    "investments": "Финансы",
    "health": "Здоровье",
    "fitness": "Здоровье",
    "wellness": "Здоровье",
    "learning": "Обучение",
    "education": "Обучение",
    "study": "Обучение",
    "course": "Обучение",
    "courses": "Обучение",
    "work": "Работа",
    "business": "Работа",
    "job": "Работа",
    "operations": "Работа",
    "creative": "Творчество",
    "creativity": "Творчество",
    "design": "Творчество",
    "writing": "Творчество",
    "art": "Творчество",
    "misc": "Разное",
    "miscellaneous": "Разное",
    "other": "Разное",
}

HEURISTIC_KEYWORDS = {
    "Технологии": (
        "ai", "llm", "openai", "gemini", "нейросет", "искусственн", "python", "код",
        "программ", "api", "github", "docker", "сервер", "бот", "framework", "agent",
        "автоматизац", "тест", "software", "browser",
    ),
    "Финансы": (
        "etf", "акци", "облигац", "инвест", "бюджет", "деньг", "налог", "банк",
        "крипт", "доход", "расход", "portfolio", "emergency fund", "finance",
    ),
    "Здоровье": (
        "сон", "спорт", "трениров", "зал", "питани", "здоров", "врач", "медиц",
        "диета", "привычк", "fitness", "sleep", "nutrition", "health",
    ),
    "Обучение": (
        "курс", "лекци", "конспект", "обуч", "учеб", "туториал", "гайд", "книг",
        "исследован", "framework", "разбор", "шпаргал", "lesson", "course", "lecture",
        "tutorial", "learn", "study", "jtbd",
    ),
    "Работа": (
        "созвон", "встреч", "дедлайн", "задач", "проект", "клиент", "контракт",
        "подрядчик", "команд", "найм", "roadmap", "meeting", "deadline", "contract",
        "client", "task", "operations",
    ),
    "Творчество": (
        "дизайн", "лендинг", "hero", "cta", "текст", "сценар", "визуаль", "музык",
        "арт", "рисунк", "идея", "контент", "creative", "design", "writing", "landing",
    ),
}

STOPWORDS = {
    "the", "and", "for", "with", "this", "that", "как", "для", "или", "про", "что",
    "это", "его", "она", "они", "новый", "новая", "новое", "сейчас", "завтра",
}


def _strip_code_blocks(text: str | None) -> str:
    """Strip markdown code block fences from LLM response."""
    if not text:
        return ""
    text = text.strip()
    text = _CODE_BLOCK_RE.sub("", text, count=1)
    text = _CODE_BLOCK_END_RE.sub("", text, count=1)
    return text.strip()


def _extract_json_object(text: str | None) -> str:
    text = _strip_code_blocks(text)
    if not text:
        return ""
    if text.startswith("{") and text.endswith("}"):
        return text
    match = _JSON_OBJECT_RE.search(text)
    return match.group(0).strip() if match else text


def _category_key(value: str | None) -> str:
    """Normalize category names for comparison without emoji/punctuation noise."""
    if not value:
        return ""
    chars = []
    for char in str(value).strip():
        category = unicodedata.category(char)
        if category[0] in {"P", "S"}:
            chars.append(" ")
        else:
            chars.append(char)
    return " ".join("".join(chars).casefold().split())


def _match_existing_category(category: str | None, existing_categories: list[dict]) -> dict | None:
    if not category or not existing_categories:
        return None

    by_key = {_category_key(c["name"]): c for c in existing_categories}
    key = _category_key(category)
    if key in by_key:
        return by_key[key]

    alias = CATEGORY_ALIASES.get(key)
    if alias and _category_key(alias) in by_key:
        return by_key[_category_key(alias)]

    for cat_key, cat in by_key.items():
        if cat_key and (cat_key in key or key in cat_key):
            return cat

    matches = difflib.get_close_matches(key, list(by_key), n=1, cutoff=0.82)
    return by_key[matches[0]] if matches else None


def _format_category_catalog(existing_categories: list[dict]) -> str:
    if not existing_categories:
        return "No categories yet"

    lines = []
    for cat in existing_categories:
        name = cat["name"]
        emoji = cat.get("emoji", "📁")
        guidance = CATEGORY_GUIDANCE.get(
            name,
            f"custom category named '{name}'; use only when the post strongly matches this name",
        )
        count = cat.get("item_count")
        count_part = f", saved items: {count}" if count is not None else ""
        lines.append(f'- "{name}" {emoji}: {guidance}{count_part}')
    return "\n".join(lines)


def _normalize_tags(raw_tags, existing_tags: list[str]) -> list[str]:
    if not raw_tags:
        return []
    if isinstance(raw_tags, str):
        raw_tags = [part for part in re.split(r"[,;]", raw_tags) if part.strip()]
    if not isinstance(raw_tags, list):
        return []

    existing_by_key = {_normalize_tag(tag): tag for tag in existing_tags}
    normalized = []
    seen = set()
    for tag in raw_tags:
        clean = _normalize_tag(str(tag))
        if not clean or clean in seen:
            continue
        normalized.append(existing_by_key.get(clean, clean))
        seen.add(clean)
        if len(normalized) == 3:
            break
    return normalized


def _normalize_tag(tag: str) -> str:
    tag = tag.strip().casefold().lstrip("#")
    tag = re.sub(r"[\s\-]+", "_", tag)
    tag = _NON_TAG_CHARS_RE.sub("_", tag)
    tag = re.sub(r"_+", "_", tag).strip("_")
    return tag[:40]


def _clean_summary(summary: str | None, content_text: str) -> str:
    text = (summary or "").strip()
    if not text:
        text = _fallback_summary(content_text)
    return " ".join(text.split())[:220]


def _fallback_summary(content_text: str) -> str:
    for line in content_text.splitlines():
        line = line.strip()
        if line:
            return line[:180]
    return ""


def _category_names(existing_categories: list[dict]) -> set[str]:
    return {_category_key(c["name"]) for c in existing_categories}


def _heuristic_category(content_text: str, existing_categories: list[dict]) -> dict | None:
    if not existing_categories:
        return None

    text = f" {content_text.casefold()} "
    available = _category_names(existing_categories)
    scores: dict[str, int] = {}

    for cat in existing_categories:
        cat_key = _category_key(cat["name"])
        if cat_key and cat_key in text:
            scores[cat["name"]] = scores.get(cat["name"], 0) + 6

    for cat_name, keywords in HEURISTIC_KEYWORDS.items():
        if _category_key(cat_name) not in available:
            continue
        score = 0
        for keyword in keywords:
            if keyword.casefold() in text:
                score += 2 if len(keyword) > 3 else 1
        if score:
            scores[cat_name] = scores.get(cat_name, 0) + score

    if not scores:
        return _match_existing_category("Разное", existing_categories)

    best_name = max(scores, key=scores.get)
    return _match_existing_category(best_name, existing_categories)


def _heuristic_tags(content_text: str, existing_tags: list[str]) -> list[str]:
    tokens = re.findall(r"[A-Za-zА-Яа-яЁё0-9][A-Za-zА-Яа-яЁё0-9_\-]{2,}", content_text.casefold())
    tags = []
    seen = set()
    for token in tokens:
        clean = _normalize_tag(token)
        if not clean or clean in STOPWORDS or clean in seen:
            continue
        tags.append(clean)
        seen.add(clean)
        if len(tags) == 3:
            break
    return _normalize_tags(tags, existing_tags)


def heuristic_classify_content(
    content_text: str,
    existing_categories: list[dict],
    existing_tags: list[str] | None = None,
) -> dict:
    """Deterministic fallback when AI is unavailable or returns an unusable category."""
    existing_tags = existing_tags or []
    category = _heuristic_category(content_text, existing_categories)
    if not category:
        category = {"name": "Разное", "emoji": "📥"}
    return {
        "category": category["name"],
        "emoji": category.get("emoji", "📁"),
        "tags": _heuristic_tags(content_text, existing_tags),
        "summary": _fallback_summary(content_text),
    }


def _coerce_result(
    raw_result: dict,
    content_text: str,
    existing_categories: list[dict],
    existing_tags: list[str],
) -> dict:
    category = _match_existing_category(raw_result.get("category"), existing_categories)
    if not category:
        category = _heuristic_category(content_text, existing_categories)
    if not category:
        category = {"name": "Разное", "emoji": "📥"}

    return {
        "category": category["name"],
        "emoji": category.get("emoji") or raw_result.get("emoji") or "📁",
        "tags": _normalize_tags(raw_result.get("tags", []), existing_tags),
        "summary": _clean_summary(raw_result.get("summary"), content_text),
    }


async def classify_content(
    content_text: str,
    existing_categories: list[dict],
    existing_tags: list[str],
) -> dict | None:
    """Classify content using OpenRouter API."""
    if not config.openrouter_api_key:
        return None

    categories_str = _format_category_catalog(existing_categories)
    tags_str = ", ".join(existing_tags[:20]) or "No tags yet"

    user_prompt = (
        f"Category catalog:\n{categories_str}\n\n"
        f"Frequently used tags: {tags_str}"
        f"\n\nContent:\n{content_text[:2500]}"
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
        "temperature": 0.1,
        "max_tokens": 300,
        "response_format": {"type": "json_object"},
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
                        logger.warning("Model %s returned %s, trying next: %s", model, resp.status, await resp.text())
                        continue
                    data = await resp.json()

            text = data["choices"][0]["message"].get("content")
            if not text:
                logger.warning("Model %s returned empty content, trying next", model)
                continue
            text = _extract_json_object(text)

            result = json.loads(text)
            if not isinstance(result, dict):
                logger.warning("AI classification returned non-object JSON with model %s", model)
                continue
            return _coerce_result(result, content_text, existing_categories, existing_tags)
        except asyncio.TimeoutError:
            logger.warning("AI classification timeout with model %s, trying next", model)
            continue
        except aiohttp.ClientError as e:
            logger.warning("AI classification network error with model %s: %s, trying next", model, e)
            continue
        except json.JSONDecodeError as e:
            logger.warning("AI classification JSON parse error with model %s: %s, trying next", model, e)
            continue
        except KeyError as e:
            logger.warning("AI classification missing key with model %s: %s, trying next", model, e)
            continue
    return None
