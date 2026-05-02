"""OCR service — extract text from images via Gemini Flash vision."""
from __future__ import annotations

import asyncio
import base64
import logging
from io import BytesIO

import aiohttp
from aiogram import Bot

from savebot.config import config

logger = logging.getLogger(__name__)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

OCR_PROMPT = "Extract ALL text from this image exactly as written. Text may be in Russian, English, or mixed. Return ONLY the extracted text, preserving line breaks. If there is no text, return empty string. Ignore decorative elements, logos, and graphics — only extract readable text."


async def extract_text_from_image(bot: Bot, file_id: str) -> str | None:
    """Download image from Telegram and extract text via Gemini Flash vision.

    Flow:
      Telegram file_id → bot.download() → base64 → OpenRouter vision → text

    Returns extracted text or None on failure.
    """
    if not config.openrouter_api_key:
        return None

    # Download image from Telegram
    try:
        file = await bot.get_file(file_id)
        buf = BytesIO()
        await bot.download_file(file.file_path, buf)
        image_bytes = buf.getvalue()
    except Exception as e:
        logger.error("Failed to download image %s: %s", file_id, e)
        return None

    if not image_bytes:
        return None

    image_b64 = base64.b64encode(image_bytes).decode("utf-8")

    # Call OpenRouter with vision content
    headers = {
        "Authorization": f"Bearer {config.openrouter_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": config.ocr_model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": OCR_PROMPT},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
                    },
                ],
            }
        ],
        "temperature": 0.1,
        "max_tokens": 1000,
    }

    for attempt in range(2):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    OPENROUTER_URL,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    if resp.status != 200:
                        logger.error("OCR API error: %s", resp.status)
                        return None
                    data = await resp.json()

            text = data["choices"][0]["message"]["content"].strip()
            return text if text else None
        except asyncio.TimeoutError:
            logger.warning("OCR timeout (attempt %d/2)", attempt + 1)
            if attempt == 0:
                await asyncio.sleep(2)
                continue
            return None
        except (aiohttp.ClientError, KeyError) as e:
            logger.error("OCR error: %s", e)
            return None
    return None
