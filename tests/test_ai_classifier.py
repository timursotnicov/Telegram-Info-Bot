"""Tests for AI classifier service (all API calls mocked)."""
import asyncio
import json

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers to build mock HTTP responses
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


def _ok_json_payload(category="Test", emoji="📁", tags=None, summary="A summary"):
    tags = tags or ["tag1"]
    return {
        "choices": [{
            "message": {
                "content": json.dumps(
                    {"category": category, "emoji": emoji, "tags": tags, "summary": summary}
                )
            }
        }]
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_classify_content_success():
    """Successful classification returns structured dict."""
    from savebot.services.ai_classifier import classify_content

    resp = _mock_response(200, _ok_json_payload(category="AI", tags=["ml", "llm"]))
    session = _mock_session(resp)

    with patch("aiohttp.ClientSession", return_value=session), \
         patch("savebot.services.ai_classifier.config") as cfg:
        cfg.openrouter_api_key = "test-key"
        cfg.ai_model = "model-a"
        cfg.ai_fallback_models = ["model-a"]

        result = await classify_content("Some text", [{"name": "Cat", "emoji": "📁"}], ["tag1"])

    assert result is not None
    assert result["category"] == "AI"
    assert result["tags"] == ["ml", "llm"]
    assert result["emoji"] == "📁"


@pytest.mark.asyncio
async def test_classify_content_rate_limit_fallback():
    """429 on first model triggers fallback to next model."""
    from savebot.services.ai_classifier import classify_content

    resp_429 = _mock_response(429)
    session_429 = _mock_session(resp_429)

    resp_ok = _mock_response(200, _ok_json_payload(category="Fallback"))
    session_ok = _mock_session(resp_ok)

    # Two sessions: first returns 429, second returns 200
    sessions = iter([session_429, session_ok])

    with patch("aiohttp.ClientSession", side_effect=lambda: next(sessions)), \
         patch("savebot.services.ai_classifier.config") as cfg, \
         patch("asyncio.sleep", new_callable=AsyncMock):
        cfg.openrouter_api_key = "test-key"
        cfg.ai_model = "model-a"
        cfg.ai_fallback_models = ["model-a", "model-b"]

        result = await classify_content("text", [], [])

    assert result is not None
    assert result["category"] == "Fallback"


@pytest.mark.asyncio
async def test_classify_content_malformed_json():
    """Malformed JSON response returns None."""
    from savebot.services.ai_classifier import classify_content

    resp = _mock_response(200, {
        "choices": [{"message": {"content": "not valid json {{"}}]
    })
    session = _mock_session(resp)

    with patch("aiohttp.ClientSession", return_value=session), \
         patch("savebot.services.ai_classifier.config") as cfg:
        cfg.openrouter_api_key = "test-key"
        cfg.ai_model = "model-a"
        cfg.ai_fallback_models = ["model-a"]

        result = await classify_content("text", [], [])

    assert result is None


@pytest.mark.asyncio
async def test_classify_content_timeout():
    """Timeout exhausts all models and returns None."""
    from savebot.services.ai_classifier import classify_content

    session = AsyncMock()
    session.post = MagicMock(side_effect=asyncio.TimeoutError)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)

    with patch("aiohttp.ClientSession", return_value=session), \
         patch("savebot.services.ai_classifier.config") as cfg:
        cfg.openrouter_api_key = "test-key"
        cfg.ai_model = "model-a"
        cfg.ai_fallback_models = ["model-a"]

        result = await classify_content("text", [], [])

    assert result is None


@pytest.mark.asyncio
async def test_classify_content_no_api_key():
    """Returns None immediately when API key is empty."""
    from savebot.services.ai_classifier import classify_content

    with patch("savebot.services.ai_classifier.config") as cfg:
        cfg.openrouter_api_key = ""

        result = await classify_content("text", [], [])

    assert result is None


@pytest.mark.asyncio
async def test_tag_normalization_hyphens_to_underscores():
    """Hyphens in tags are replaced with underscores."""
    from savebot.services.ai_classifier import classify_content

    payload = _ok_json_payload(tags=["machine-learning", "deep-learning", "nlp"])
    resp = _mock_response(200, payload)
    session = _mock_session(resp)

    with patch("aiohttp.ClientSession", return_value=session), \
         patch("savebot.services.ai_classifier.config") as cfg:
        cfg.openrouter_api_key = "test-key"
        cfg.ai_model = "model-a"
        cfg.ai_fallback_models = ["model-a"]

        result = await classify_content("text", [], [])

    assert result["tags"] == ["machine_learning", "deep_learning", "nlp"]


@pytest.mark.asyncio
async def test_markdown_code_block_stripping():
    """Response wrapped in ```json ... ``` is still parsed correctly."""
    from savebot.services.ai_classifier import classify_content

    inner = '{"category": "Wrapped", "emoji": "📦", "tags": ["wrap"], "summary": "ok"}'
    wrapped = f"```json\n{inner}\n```"

    resp = _mock_response(200, {
        "choices": [{"message": {"content": wrapped}}]
    })
    session = _mock_session(resp)

    with patch("aiohttp.ClientSession", return_value=session), \
         patch("savebot.services.ai_classifier.config") as cfg:
        cfg.openrouter_api_key = "test-key"
        cfg.ai_model = "model-a"
        cfg.ai_fallback_models = ["model-a"]

        result = await classify_content("text", [], [])

    assert result is not None
    assert result["category"] == "Wrapped"
