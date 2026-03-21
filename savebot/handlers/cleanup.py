"""AI-powered category cleanup handlers."""
from __future__ import annotations

import html
import logging

from aiogram import F, Router, types
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from savebot.db import queries
from savebot.services.ai_cleanup import analyze_categories

router = Router()
logger = logging.getLogger(__name__)

# In-memory storage for pending cleanup plans (user_id -> list of suggestions)
_pending_plans: dict[int, list[dict]] = {}


@router.callback_query(F.data == "settings_cleanup")
async def on_cleanup_start(callback: types.CallbackQuery, db=None):
    """Start AI category analysis."""
    user_id = callback.from_user.id
    await callback.message.edit_text("\U0001f9f9 <b>Анализирую категории...</b>", parse_mode="HTML")
    await callback.answer()

    plan = await analyze_categories(db, user_id)
    if not plan:
        await callback.message.edit_text(
            "\u26a0\ufe0f Не удалось проанализировать категории. Попробуйте позже.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="\U0001f519 Назад", callback_data="settings_back")],
            ]),
            parse_mode="HTML",
        )
        return

    _pending_plans[user_id] = plan
    await _show_next_suggestion(callback.message, user_id, 0)


async def _show_next_suggestion(message: types.Message, user_id: int, index: int):
    """Show the next suggestion in the cleanup plan."""
    plan = _pending_plans.get(user_id, [])

    if index >= len(plan):
        # All done
        _pending_plans.pop(user_id, None)
        await message.edit_text(
            "\u2705 <b>Уборка завершена!</b>",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="\U0001f519 К настройкам", callback_data="settings_back")],
            ]),
            parse_mode="HTML",
        )
        return

    s = plan[index]
    action = s.get("action", "")
    reason = html.escape(s.get("reason", ""))

    if action == "merge":
        text = (
            f"\U0001f9f9 <b>Предложение {index + 1}/{len(plan)}</b>\n\n"
            f"\U0001f4c2 <b>{html.escape(s['category'])}</b> \u2192 <b>{html.escape(s['target'])}</b>\n"
            f"Причина: {reason}"
        )
    elif action == "delete":
        text = (
            f"\U0001f9f9 <b>Предложение {index + 1}/{len(plan)}</b>\n\n"
            f"\U0001f5d1 Удалить: <b>{html.escape(s['category'])}</b>\n"
            f"Причина: {reason}"
        )
    elif action == "create":
        emoji = s.get("emoji", "\U0001f4c1")
        text = (
            f"\U0001f9f9 <b>Предложение {index + 1}/{len(plan)}</b>\n\n"
            f"\u2795 Создать: {emoji} <b>{html.escape(s['name'])}</b>\n"
            f"Перенести {len(s.get('items', []))} записей\n"
            f"Причина: {reason}"
        )
    elif action == "keep":
        text = (
            f"\U0001f9f9 <b>Предложение {index + 1}/{len(plan)}</b>\n\n"
            f"\u2705 Оставить: <b>{html.escape(s['category'])}</b>\n"
            f"Причина: {reason}"
        )
    else:
        # Skip unknown actions
        await _show_next_suggestion(message, user_id, index + 1)
        return

    buttons = [
        [
            InlineKeyboardButton(text="\u2705 Принять", callback_data=f"cleanup_yes:{index}"),
            InlineKeyboardButton(text="\u23ed Пропустить", callback_data=f"cleanup_skip:{index}"),
        ],
        [InlineKeyboardButton(text="\u23f9 Закончить", callback_data="cleanup_done")],
    ]

    await message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")


@router.callback_query(F.data.startswith("cleanup_yes:"))
async def on_cleanup_accept(callback: types.CallbackQuery, db=None):
    """Accept a cleanup suggestion and execute it."""
    index = int(callback.data.split(":")[1])
    user_id = callback.from_user.id
    plan = _pending_plans.get(user_id, [])

    if index >= len(plan):
        await callback.answer("Ошибка")
        return

    s = plan[index]
    action = s.get("action", "")

    # Guard: never merge/delete default categories
    _default_names = {name for name, _ in queries.DEFAULT_CATEGORIES}

    try:
        if action == "merge":
            if s.get("category") in _default_names:
                await callback.answer("\u26a0\ufe0f Нельзя удалить базовую категорию")
                await _show_next_suggestion(callback.message, user_id, index + 1)
                return
            source_cat = await queries.get_category_by_name(db, user_id, s["category"])
            target_cat = await queries.get_category_by_name(db, user_id, s["target"])
            if source_cat and target_cat:
                moved = await queries.merge_categories(db, user_id, source_cat["id"], target_cat["id"])
                await callback.answer(f"\u2705 Перенесено {moved} записей")
            else:
                await callback.answer("\u26a0\ufe0f Категория не найдена")

        elif action == "delete":
            if s.get("category") in _default_names:
                await callback.answer("\u26a0\ufe0f Нельзя удалить базовую категорию")
                await _show_next_suggestion(callback.message, user_id, index + 1)
                return
            cat = await queries.get_category_by_name(db, user_id, s["category"])
            if cat:
                await queries.delete_category(db, user_id, cat["id"])
                await callback.answer("\u2705 Удалено")
            else:
                await callback.answer("\u26a0\ufe0f Категория не найдена")

        elif action == "create":
            emoji = s.get("emoji", "\U0001f4c1")
            cat = await queries.get_or_create_category(db, user_id, s["name"], emoji)
            for item_id in s.get("items", []):
                await queries.update_item_category(db, user_id, int(item_id), cat["id"])
            await callback.answer(f"\u2705 Создано, перенесено {len(s.get('items', []))} записей")

        elif action == "keep":
            await callback.answer("\u2705 Оставлено")

    except Exception as e:
        logger.error("Cleanup action failed: %s", e)
        await callback.answer("\u26a0\ufe0f Ошибка при выполнении")

    await _show_next_suggestion(callback.message, user_id, index + 1)


@router.callback_query(F.data.startswith("cleanup_skip:"))
async def on_cleanup_skip(callback: types.CallbackQuery, db=None):
    """Skip a suggestion."""
    index = int(callback.data.split(":")[1])
    user_id = callback.from_user.id
    await callback.answer("\u23ed Пропущено")
    await _show_next_suggestion(callback.message, user_id, index + 1)


@router.callback_query(F.data == "cleanup_done")
async def on_cleanup_done(callback: types.CallbackQuery, db=None):
    """End cleanup early."""
    user_id = callback.from_user.id
    _pending_plans.pop(user_id, None)
    await callback.message.edit_text(
        "\u2705 <b>Уборка завершена!</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="\U0001f519 К настройкам", callback_data="settings_back")],
        ]),
        parse_mode="HTML",
    )
    await callback.answer()
