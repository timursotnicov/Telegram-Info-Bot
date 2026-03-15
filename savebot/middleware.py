"""Error handling middleware."""
from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update

logger = logging.getLogger(__name__)


class ErrorMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        try:
            return await handler(event, data)
        except Exception as e:
            # Extract context for logging
            user_id = None
            message_text = None
            if isinstance(event, Update):
                if event.message:
                    user_id = event.message.from_user.id if event.message.from_user else None
                    message_text = event.message.text
                elif event.callback_query:
                    user_id = event.callback_query.from_user.id if event.callback_query.from_user else None
                    message_text = event.callback_query.data

            logger.error(
                "Handler error: %s | user_id=%s | text=%s",
                e, user_id, message_text[:100] if message_text else None,
                exc_info=True,
            )

            # Try to send user-friendly message
            try:
                bot = data.get("bot")
                if bot and user_id:
                    await bot.send_message(
                        user_id,
                        "\u26a0\ufe0f \u041f\u0440\u043e\u0438\u0437\u043e\u0448\u043b\u0430 \u043e\u0448\u0438\u0431\u043a\u0430. \u041f\u043e\u043f\u0440\u043e\u0431\u0443\u0439\u0442\u0435 \u0435\u0449\u0451 \u0440\u0430\u0437.",
                    )
            except Exception:
                pass  # Don't fail on notification failure
