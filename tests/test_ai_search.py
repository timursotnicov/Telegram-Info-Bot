"""Tests for AI search service (all API calls mocked)."""
import asyncio
import json

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_response(status=200, json_data=None, text_data=""):
    resp = AsyncMock()
    resp.status = status
    resp.json = AsyncMock(return_value=json_data or {})
    resp.text = AsyncMock(return_value=text_data)
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    return resp


def _mock_session(response):
    session = AsyncMock()
    session.post = MagicMock(return_value=response)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    return session


def _chat_payload(content: str):
    return {"choices": [{"message": {"content": content}}]}


# ---------------------------------------------------------------------------
# parse_search_query tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_parse_search_query_success():
    """Valid JSON response is parsed into structured filters."""
    from savebot.services.ai_search import parse_search_query

    answer = json.dumps({
        "keywords": ["нейросети"],
        "date_from": "2026-03-09",
        "date_to": "2026-03-16",
        "category_hint": None,
        "tag_hint": None,
    })
    resp = _mock_response(200, _chat_payload(answer))
    session = _mock_session(resp)

    with patch("aiohttp.ClientSession", return_value=session), \
         patch("savebot.services.ai_search.config") as cfg:
        cfg.openrouter_api_key = "test-key"
        cfg.ai_model = "model-a"
        cfg.ai_fallback_models = ["model-a"]

        result = await parse_search_query("нейросети за последнюю неделю")

    assert result is not None
    assert result["keywords"] == ["нейросети"]
    assert result["date_from"] == "2026-03-09"
    assert result["date_to"] == "2026-03-16"
    assert result["category_hint"] is None


@pytest.mark.asyncio
async def test_parse_search_query_api_failure():
    """Non-200 response makes parse_search_query return None."""
    from savebot.services.ai_search import parse_search_query

    resp = _mock_response(500)
    session = _mock_session(resp)

    with patch("aiohttp.ClientSession", return_value=session), \
         patch("savebot.services.ai_search.config") as cfg:
        cfg.openrouter_api_key = "test-key"
        cfg.ai_model = "model-a"
        cfg.ai_fallback_models = ["model-a"]

        result = await parse_search_query("anything")

    assert result is None


@pytest.mark.asyncio
async def test_parse_search_query_normalizes_null_strings():
    """String "null" and empty strings are normalized to None."""
    from savebot.services.ai_search import parse_search_query

    answer = json.dumps({
        "keywords": ["test"],
        "date_from": "null",
        "date_to": "",
        "category_hint": "null",
        "tag_hint": None,
    })
    resp = _mock_response(200, _chat_payload(answer))
    session = _mock_session(resp)

    with patch("aiohttp.ClientSession", return_value=session), \
         patch("savebot.services.ai_search.config") as cfg:
        cfg.openrouter_api_key = "test-key"
        cfg.ai_model = "model-a"
        cfg.ai_fallback_models = ["model-a"]

        result = await parse_search_query("test")

    assert result["date_from"] is None
    assert result["date_to"] is None
    assert result["category_hint"] is None
    assert result["tag_hint"] is None


# ---------------------------------------------------------------------------
# synthesize_answer tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_synthesize_answer_success():
    """Returns synthesized text from API."""
    from savebot.services.ai_search import synthesize_answer

    resp = _mock_response(200, _chat_payload("Here is the answer (см. #1, #2)"))
    session = _mock_session(resp)

    items = [
        {"id": 1, "ai_summary": "Summary one", "tags": ["a"], "created_at": "2026-03-10"},
        {"id": 2, "ai_summary": "Summary two", "tags": ["b"], "created_at": "2026-03-11"},
    ]

    with patch("aiohttp.ClientSession", return_value=session), \
         patch("savebot.services.ai_search.config") as cfg:
        cfg.openrouter_api_key = "test-key"
        cfg.ai_model = "model-a"
        cfg.ai_fallback_models = ["model-a"]

        result = await synthesize_answer("What did I save?", items)

    assert result is not None
    assert "#1" in result or "#2" in result


@pytest.mark.asyncio
async def test_synthesize_answer_empty_items():
    """Empty items list returns None without calling API."""
    from savebot.services.ai_search import synthesize_answer

    result = await synthesize_answer("question", [])
    assert result is None


# ---------------------------------------------------------------------------
# _call_openrouter internal tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_call_openrouter_system_merged_into_user():
    """System prompt is merged into user message (single 'user' role)."""
    from savebot.services.ai_search import _call_openrouter

    resp = _mock_response(200, _chat_payload("ok"))
    session = _mock_session(resp)

    with patch("aiohttp.ClientSession", return_value=session), \
         patch("savebot.services.ai_search.config") as cfg:
        cfg.openrouter_api_key = "test-key"
        cfg.ai_model = "model-a"
        cfg.ai_fallback_models = ["model-a"]

        await _call_openrouter("SYSTEM_PART", "USER_PART")

    # Inspect the payload sent to session.post
    call_kwargs = session.post.call_args
    sent_payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
    messages = sent_payload["messages"]

    assert len(messages) == 1
    assert messages[0]["role"] == "user"
    assert "SYSTEM_PART" in messages[0]["content"]
    assert "USER_PART" in messages[0]["content"]


@pytest.mark.asyncio
async def test_call_openrouter_model_fallback_on_429():
    """429 on first model triggers retry with next model."""
    from savebot.services.ai_search import _call_openrouter

    resp_429 = _mock_response(429)
    session_429 = _mock_session(resp_429)

    resp_ok = _mock_response(200, _chat_payload("success"))
    session_ok = _mock_session(resp_ok)

    sessions = iter([session_429, session_ok])

    with patch("aiohttp.ClientSession", side_effect=lambda: next(sessions)), \
         patch("savebot.services.ai_search.config") as cfg, \
         patch("asyncio.sleep", new_callable=AsyncMock):
        cfg.openrouter_api_key = "test-key"
        cfg.ai_model = "model-a"
        cfg.ai_fallback_models = ["model-a", "model-b"]

        result = await _call_openrouter("sys", "usr")

    assert result == "success"
