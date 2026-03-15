"""Management handlers: /edit, /delete, /stats, /categories, /export, /start, /help, /clear."""

from __future__ import annotations

import json
import logging
from collections import defaultdict

from aiogram import F, Router, types
from aiogram.errors import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from savebot.db import queries
from savebot.db.state_store import set_state

router = Router()
logger = logging.getLogger(__name__)

# Track bot message IDs per user for /clear (in-memory, max 100 per user)
_bot_messages: dict[int, list[int]] = defaultdict(list)
_MAX_TRACKED = 100


def track_message(user_id: int, message_id: int):
    """Track a bot message ID for later cleanup via /clear."""
    msgs = _bot_messages[user_id]
    msgs.append(message_id)
    if len(msgs) > _MAX_TRACKED:
        _bot_messages[user_id] = msgs[-_MAX_TRACKED:]


# ── /start and /help ────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(message: types.Message, **kwargs):
    result = await message.reply(
        "👋 <b>Привет! Я SaveBot</b> — твоя вторая память.\n\n"
        "Просто отправь мне текст, ссылку, фото или файл — "
        "я сохраню и организую автоматически.\n\n"
        "📂 Навигация: /browse /tags /map\n"
        "🔍 Поиск: /search /ask\n"
        "📌 Быстрый доступ: /recent /pinned /readlist\n"
        "⚙️ Управление: /settings /stats /export\n"
        "ℹ️ Подробнее: /help",
        parse_mode="HTML",
    )
    track_message(message.from_user.id, result.message_id)


@router.message(Command("help"))
async def cmd_help(message: types.Message, **kwargs):
    result = await message.reply(
        "📖 <b>Все команды SaveBot:</b>\n\n"
        "<b>📂 Навигация</b>\n"
        "/browse — просмотр по категориям\n"
        "/tags — облако тегов\n"
        "/map — карта знаний\n"
        "/forgotten — забытые записи\n\n"
        "<b>🔍 Поиск</b>\n"
        "/search &lt;запрос&gt; — поиск по записям\n"
        "/ask &lt;вопрос&gt; — спросить базу знаний (AI)\n\n"
        "<b>📌 Быстрый доступ</b>\n"
        "/recent — последние 10 записей\n"
        "/pinned — закреплённые записи\n"
        "/readlist — список чтения\n\n"
        "<b>✏️ Редактирование</b>\n"
        "/edit &lt;id&gt; — редактировать запись\n"
        "/delete &lt;id&gt; — удалить запись\n"
        "/pin &lt;id&gt; — закрепить запись\n"
        "/unpin &lt;id&gt; — открепить запись\n"
        "/markread &lt;id&gt; — отметить прочитанным\n\n"
        "<b>⚙️ Управление</b>\n"
        "/categories — управление категориями\n"
        "/stats — статистика\n"
        "/export — экспорт в JSON\n"
        "/settings — настройки\n\n"
        "<b>🧹 Прочее</b>\n"
        "/clear — очистить сообщения бота\n"
        "/clearall — отметить всё прочитанным",
        parse_mode="HTML",
    )
    track_message(message.from_user.id, result.message_id)


# ── /clear ─────────────────────────────────────────────────

@router.message(Command("clear"))
async def cmd_clear(message: types.Message, **kwargs):
    user_id = message.from_user.id
    msg_ids = _bot_messages.pop(user_id, [])
    deleted = 0
    for msg_id in msg_ids:
        try:
            await message.bot.delete_message(chat_id=message.chat.id, message_id=msg_id)
            deleted += 1
        except TelegramBadRequest:
            pass  # Message too old (>48h) or already deleted
    # Also try to delete the /clear command message itself
    try:
        await message.delete()
    except TelegramBadRequest:
        pass
    if deleted == 0 and not msg_ids:
        result = await message.answer("🧹 Нет сообщений для очистки.")
        track_message(user_id, result.message_id)


# ── /stats ──────────────────────────────────────────────────

@router.message(Command("stats"))
async def cmd_stats(message: types.Message, db=None, **kwargs):
    user_id = message.from_user.id
    stats = await queries.get_stats(db, user_id)
    await message.reply(
        f"📊 <b>Статистика:</b>\n\n"
        f"📝 Записей: {stats['items']}\n"
        f"📂 Категорий: {stats['categories']}\n"
        f"🏷 Тегов: {stats['tags']}",
        parse_mode="HTML",
    )


# ── /categories ─────────────────────────────────────────────

@router.message(Command("categories"))
async def cmd_categories(message: types.Message, db=None, **kwargs):
    user_id = message.from_user.id
    categories = await queries.get_all_categories(db, user_id)
    if not categories:
        await message.reply("Категорий пока нет.")
        return

    buttons = []
    for cat in categories:
        emoji = cat.get("emoji", "📁")
        buttons.append([
            InlineKeyboardButton(
                text=f"{emoji} {cat['name']} ({cat['item_count']})",
                callback_data=f"cat_info:{cat['id']}",
            ),
            InlineKeyboardButton(
                text="✏️",
                callback_data=f"cat_rename:{cat['id']}",
            ),
            InlineKeyboardButton(
                text="🗑",
                callback_data=f"cat_delete:{cat['id']}",
            ),
        ])

    await message.reply(
        "📂 <b>Управление категориями:</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("cat_delete:"))
async def on_cat_delete(callback: types.CallbackQuery, db=None):
    cat_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id
    affected = await queries.delete_category(db, user_id, cat_id)
    await callback.message.edit_text(
        f"🗑 Категория удалена. {affected} записей перемещены в «без категории».",
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("cat_rename:"))
async def on_cat_rename(callback: types.CallbackQuery, db=None):
    await callback.message.edit_text(
        "Введите новое название категории:",
        parse_mode="HTML",
    )
    await set_state(db, f"rename_cat_{callback.from_user.id}", callback.from_user.id, "rename_cat", {"cat_id": int(callback.data.split(":")[1])})
    await callback.answer()


# ── /edit ───────────────────────────────────────────────────

@router.message(Command("edit"))
async def cmd_edit(message: types.Message, db=None, **kwargs):
    user_id = message.from_user.id
    parts = message.text.split()
    if len(parts) < 2:
        await message.reply("Использование: /edit <id>")
        return

    try:
        item_id = int(parts[1])
    except ValueError:
        await message.reply("ID должен быть числом.")
        return

    item = await queries.get_item(db, user_id, item_id)
    if not item:
        await message.reply(f"Запись #{item_id} не найдена.")
        return

    tags_str = " ".join(f"#{t}" for t in item.get("tags", []))
    text = (
        f"📝 <b>Запись #{item_id}</b>\n"
        f"Тип: {item['content_type']}\n"
        f"Теги: {tags_str}\n"
        f"Текст: {item['content_text'][:200]}\n"
    )

    categories = await queries.get_all_categories(db, user_id)
    buttons = []
    row = []
    for cat in categories:
        emoji = cat.get("emoji", "📁")
        row.append(InlineKeyboardButton(
            text=f"{emoji} {cat['name']}",
            callback_data=f"edit_cat:{item_id}:{cat['id']}",
        ))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    await message.reply(
        text + "\nВыберите новую категорию:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("edit_cat:"))
async def on_edit_category(callback: types.CallbackQuery, db=None):
    parts = callback.data.split(":")
    item_id = int(parts[1])
    cat_id = int(parts[2])
    user_id = callback.from_user.id

    await queries.update_item_category(db, user_id, item_id, cat_id)
    await callback.message.edit_text(
        f"✅ Категория записи #{item_id} обновлена.",
        parse_mode="HTML",
    )
    await callback.answer()


# ── /delete ─────────────────────────────────────────────────

@router.message(Command("delete"))
async def cmd_delete(message: types.Message, db=None, **kwargs):
    parts = message.text.split()
    if len(parts) < 2:
        await message.reply("Использование: /delete <id>")
        return

    try:
        item_id = int(parts[1])
    except ValueError:
        await message.reply("ID должен быть числом.")
        return

    buttons = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"confirm_delete:{item_id}"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_delete"),
    ]])

    await message.reply(
        f"Удалить запись #{item_id}?",
        reply_markup=buttons,
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("confirm_delete:"))
async def on_confirm_delete(callback: types.CallbackQuery, db=None):
    item_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id
    deleted = await queries.delete_item(db, user_id, item_id)
    if deleted:
        await callback.message.edit_text(f"🗑 Запись #{item_id} удалена.")
    else:
        await callback.message.edit_text(f"Запись #{item_id} не найдена.")
    await callback.answer()


@router.callback_query(F.data == "cancel_delete")
async def on_cancel_delete(callback: types.CallbackQuery, **kwargs):
    await callback.message.edit_text("Отменено.")
    await callback.answer()


# ── /export ─────────────────────────────────────────────────

@router.message(Command("export"))
async def cmd_export(message: types.Message, db=None, **kwargs):
    user_id = message.from_user.id
    items = await queries.export_all(db, user_id)
    if not items:
        await message.reply("Нет данных для экспорта.")
        return

    export_data = json.dumps(items, ensure_ascii=False, indent=2, default=str)

    if len(export_data) > 4000:
        from io import BytesIO
        file = BytesIO(export_data.encode())
        file.name = "savebot_export.json"
        await message.reply_document(
            types.BufferedInputFile(file.getvalue(), filename="savebot_export.json"),
            caption=f"📦 Экспорт: {len(items)} записей",
        )
    else:
        await message.reply(
            f"📦 <b>Экспорт ({len(items)} записей):</b>\n\n"
            f"<pre>{export_data[:3900]}</pre>",
            parse_mode="HTML",
        )
