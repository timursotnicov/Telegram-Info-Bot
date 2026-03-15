"""SaveBot entry point — aiogram 3.x bot initialization."""

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

from savebot.config import config
from savebot.db.models import init_db
from savebot.handlers import browse, inline, manage, save, settings
from savebot.middleware import ErrorMiddleware
from savebot.scheduler import start_scheduler, stop_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def on_startup(bot: Bot, db):
    if not config.use_polling and config.webhook_host:
        webhook_url = f"{config.webhook_host}{config.webhook_path}"
        await bot.set_webhook(webhook_url)
        logger.info("Webhook set to %s", webhook_url)


async def main():
    db = await init_db(config.db_path)
    logger.info("Database initialized at %s", config.db_path)

    bot = Bot(
        token=config.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    dp = Dispatcher()

    # Error-catching middleware (runs first, wraps everything)
    dp.update.middleware(ErrorMiddleware())

    # Register routers — settings first, then manage (commands), browse, save (catch-all)
    dp.include_router(settings.router)
    dp.include_router(manage.router)
    dp.include_router(browse.router)
    dp.include_router(inline.router)
    dp.include_router(save.router)

    # Inject db into all handlers via middleware
    @dp.update.outer_middleware()
    async def db_middleware(handler, event, data):
        data["db"] = db
        return await handler(event, data)

    start_scheduler(bot, config.db_path)

    if config.use_polling:
        logger.info("Starting bot in polling mode...")
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    else:
        logger.info("Starting bot in webhook mode on port %s...", config.webhook_port)
        await on_startup(bot, db)
        app = web.Application()
        webhook_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
        webhook_handler.register(app, path=config.webhook_path)
        setup_application(app, dp, bot=bot)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", config.webhook_port)
        await site.start()
        logger.info("Webhook server started")
        await asyncio.Event().wait()

    stop_scheduler()
    await db.close()


if __name__ == "__main__":
    asyncio.run(main())
