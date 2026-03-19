"""Scheduler for periodic tasks (digests, cleanup)."""
from __future__ import annotations

import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from aiogram import Bot
import aiosqlite

from savebot.db import queries
from savebot.db.state_store import cleanup_expired
from savebot.services.digest import generate_weekly_digest, send_daily_brief

logger = logging.getLogger(__name__)

JOB_TIMEOUT_DIGEST = 120  # seconds
JOB_TIMEOUT_BRIEF = 60
JOB_TIMEOUT_CLEANUP = 30

_scheduler: AsyncIOScheduler | None = None


async def _send_digests(bot: Bot, db_path: str):
    """Send weekly digests to users whose chosen day is today."""
    import datetime
    today_weekday = datetime.datetime.now().weekday()  # 0=Mon, 6=Sun

    db = await aiosqlite.connect(db_path)
    db.row_factory = aiosqlite.Row
    try:
        users = await queries.get_all_users_with_digest(db)
        for user_pref in users:
            # Only send if today matches user's chosen digest day
            user_day = user_pref.get("digest_day", 1)  # default Monday=1
            if user_day != today_weekday:
                continue

            user_id = user_pref["user_id"]
            try:
                digest = await generate_weekly_digest(db, user_id)
                if digest:
                    await bot.send_message(user_id, digest, parse_mode="HTML")
                    week_items = await queries.get_items_this_week(db, user_id, limit=50)
                    item_ids = [it["id"] for it in week_items]
                    await queries.log_digest(db, user_id, item_ids)
                    logger.info("Digest sent to user %s", user_id)
            except Exception as e:
                logger.error("Failed to send digest to user %s: %s", user_id, e)
    finally:
        await db.close()


async def _check_daily_briefs(bot: Bot, db_path: str):
    """Send daily briefs to users whose chosen time matches the current hour."""
    import datetime
    current_hour = datetime.datetime.now().strftime("%H:00")

    db = await aiosqlite.connect(db_path)
    db.row_factory = aiosqlite.Row
    try:
        users = await queries.get_all_users_with_daily_brief(db)
        for user_pref in users:
            user_time = user_pref.get("daily_brief_time", "09:00")
            # Compare HH:00 with the user's chosen HH:MM (match on hour)
            if user_time[:2] != current_hour[:2]:
                continue

            user_id = user_pref["user_id"]
            try:
                await send_daily_brief(bot, db, user_id)
            except Exception as e:
                logger.error("Failed to send daily brief to user %s: %s", user_id, e)
    finally:
        await db.close()


async def _cleanup_states(db_path: str):
    """Clean up expired pending states."""
    db = await aiosqlite.connect(db_path)
    db.row_factory = aiosqlite.Row
    try:
        await cleanup_expired(db, max_age_minutes=60)
    finally:
        await db.close()


async def _send_digests_safe(bot: Bot, db_path: str):
    try:
        await asyncio.wait_for(_send_digests(bot, db_path), timeout=JOB_TIMEOUT_DIGEST)
    except asyncio.TimeoutError:
        logger.error("Digest job timed out after %ds", JOB_TIMEOUT_DIGEST)
    except Exception as e:
        logger.error("Digest job failed: %s", e)


async def _check_daily_briefs_safe(bot: Bot, db_path: str):
    try:
        await asyncio.wait_for(_check_daily_briefs(bot, db_path), timeout=JOB_TIMEOUT_BRIEF)
    except asyncio.TimeoutError:
        logger.error("Daily brief job timed out after %ds", JOB_TIMEOUT_BRIEF)
    except Exception as e:
        logger.error("Daily brief job failed: %s", e)


async def _cleanup_states_safe(db_path: str):
    try:
        await asyncio.wait_for(_cleanup_states(db_path), timeout=JOB_TIMEOUT_CLEANUP)
    except asyncio.TimeoutError:
        logger.error("Cleanup job timed out after %ds", JOB_TIMEOUT_CLEANUP)
    except Exception as e:
        logger.error("Cleanup job failed: %s", e)


async def _cleanup_empty_categories(db_path: str):
    """Delete empty non-default categories for all users."""
    db = await aiosqlite.connect(db_path)
    db.row_factory = aiosqlite.Row
    try:
        cursor = await db.execute("SELECT DISTINCT user_id FROM categories")
        users = [row["user_id"] for row in await cursor.fetchall()]
        for uid in users:
            deleted = await queries.delete_empty_non_default_categories(db, uid)
            if deleted:
                logger.info("Cleaned %d empty categories for user %d", deleted, uid)
    finally:
        await db.close()


async def _cleanup_empty_categories_safe(db_path: str):
    try:
        await asyncio.wait_for(_cleanup_empty_categories(db_path), timeout=JOB_TIMEOUT_CLEANUP)
    except asyncio.TimeoutError:
        logger.error("Category cleanup timed out after %ds", JOB_TIMEOUT_CLEANUP)
    except Exception as e:
        logger.error("Category cleanup failed: %s", e)


def start_scheduler(bot: Bot, db_path: str):
    """Start the async scheduler with digest and cleanup jobs."""
    global _scheduler
    _scheduler = AsyncIOScheduler()

    # Daily check at 10:00 — sends digest only to users whose chosen day is today
    _scheduler.add_job(
        _send_digests_safe,
        CronTrigger(hour=10, minute=0),
        args=[bot, db_path],
        id="daily_digest_check",
        replace_existing=True,
    )

    # Hourly check for daily briefs — sends to users whose chosen hour matches
    _scheduler.add_job(
        _check_daily_briefs_safe,
        CronTrigger(minute=0),
        args=[bot, db_path],
        id="daily_brief_check",
        replace_existing=True,
    )

    # Cleanup expired pending states — every hour
    _scheduler.add_job(
        _cleanup_states_safe,
        IntervalTrigger(hours=1),
        args=[db_path],
        id="cleanup_states",
        replace_existing=True,
    )

    # Cleanup empty non-default categories — daily at 3:00 AM
    _scheduler.add_job(
        _cleanup_empty_categories_safe,
        CronTrigger(hour=3, minute=0),
        args=[db_path],
        id="cleanup_empty_categories",
        replace_existing=True,
    )

    _scheduler.start()
    logger.info("Scheduler started with %d jobs", len(_scheduler.get_jobs()))


def stop_scheduler():
    """Stop the scheduler gracefully."""
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("Scheduler stopped")
