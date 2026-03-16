"""User preferences / settings handler."""
from __future__ import annotations

from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from savebot.db import queries

router = Router()

DAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
BRIEF_TIMES = ["08:00", "09:00", "10:00", "12:00", "18:00", "21:00"]


def _render_settings(prefs: dict) -> tuple[str, InlineKeyboardMarkup]:
    """Render settings text and keyboard from user preferences."""
    auto_save = "✅ Вкл" if prefs.get("auto_save", 1) else "❌ Выкл"
    digest = "✅ Вкл" if prefs.get("digest_enabled", 1) else "❌ Выкл"
    digest_day = DAYS[prefs.get("digest_day", 1) % 7]
    digest_time = prefs.get("digest_time", "10:00")
    brief = "✅ Вкл" if prefs.get("daily_brief_enabled", 0) else "❌ Выкл"
    brief_time = prefs.get("daily_brief_time", "09:00")

    text = (
        "⚙️ <b>Настройки</b>\n\n"
        f"💾 Авто-сохранение: {auto_save}\n"
        f"📬 Еженедельный дайджест: {digest}\n"
        f"📅 День дайджеста: {digest_day}\n"
        f"🕐 Время дайджеста: {digest_time}\n"
        f"🧠 Daily Brief: {brief}\n"
        f"⏰ Время брифа: {brief_time}\n"
    )

    rows = [
        [InlineKeyboardButton(text=f"💾 Авто-сохранение: {auto_save}", callback_data="settings_toggle:auto_save")],
        [InlineKeyboardButton(text=f"📬 Дайджест: {digest}", callback_data="settings_toggle:digest_enabled")],
        [InlineKeyboardButton(text=f"📅 День: {digest_day}", callback_data="settings_day")],
        [InlineKeyboardButton(text=f"🧠 Daily Brief: {brief}", callback_data="settings_toggle:daily_brief_enabled")],
    ]
    if prefs.get("daily_brief_enabled", 0):
        rows.append([InlineKeyboardButton(text=f"⏰ Время брифа: {brief_time}", callback_data="settings_brief_time")])

    keyboard = InlineKeyboardMarkup(inline_keyboard=rows)

    return text, keyboard


@router.message(Command("settings"))
async def cmd_settings(message: types.Message, db=None, **kwargs):
    prefs = await queries.get_user_preferences(db, message.from_user.id)
    text, keyboard = _render_settings(prefs)
    await message.reply(text, reply_markup=keyboard, parse_mode="HTML")


@router.callback_query(F.data.startswith("settings_toggle:"))
async def on_settings_toggle(callback: types.CallbackQuery, db=None):
    key = callback.data.split(":")[1]
    user_id = callback.from_user.id
    prefs = await queries.get_user_preferences(db, user_id)
    new_value = 0 if prefs.get(key, 1) else 1
    await queries.update_user_preference(db, user_id, key, new_value)

    prefs = await queries.get_user_preferences(db, user_id)
    text, keyboard = _render_settings(prefs)
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "settings_day")
async def on_settings_day(callback: types.CallbackQuery, db=None):
    buttons = []
    row = []
    for i, day in enumerate(DAYS):
        row.append(InlineKeyboardButton(text=day, callback_data=f"settings_set_day:{i}"))
        if len(row) == 4:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="settings_back")])

    await callback.message.edit_text(
        "📅 Выберите день для дайджеста:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("settings_set_day:"))
async def on_set_day(callback: types.CallbackQuery, db=None):
    day = int(callback.data.split(":")[1])
    user_id = callback.from_user.id
    await queries.update_user_preference(db, user_id, "digest_day", day)
    await callback.answer(f"День дайджеста: {DAYS[day]}")
    await on_settings_back(callback, db)


@router.callback_query(F.data == "settings_brief_time")
async def on_settings_brief_time(callback: types.CallbackQuery, db=None):
    buttons = []
    row = []
    for t in BRIEF_TIMES:
        row.append(InlineKeyboardButton(text=t, callback_data=f"settings_brief_time:{t}"))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="settings_back")])

    await callback.message.edit_text(
        "⏰ Выберите время для Daily Brief:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("settings_brief_time:"))
async def on_set_brief_time(callback: types.CallbackQuery, db=None):
    time_val = callback.data.split(":")[1] + ":" + callback.data.split(":")[2]
    user_id = callback.from_user.id
    await queries.update_user_preference(db, user_id, "daily_brief_time", time_val)
    await callback.answer(f"Время брифа: {time_val}")
    await on_settings_back(callback, db)


@router.callback_query(F.data == "settings_back")
async def on_settings_back(callback: types.CallbackQuery, db=None):
    prefs = await queries.get_user_preferences(db, callback.from_user.id)
    text, keyboard = _render_settings(prefs)
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
