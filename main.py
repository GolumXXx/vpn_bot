import asyncio
import logging
from contextlib import suppress

from aiogram import Bot, Dispatcher

from config import BOT_TOKEN
from database.db import init_db
from routers.start import router as start_router
from routers.trial import router as trial_router
from routers.payments import router as payments_router
from routers.help import router as help_router
from routers.keys import router as keys_router, reminder_loop as keys_reminder_loop
from routers.invite import router as invite_router
from routers.services import router as services_router
from routers.admin import router as admin_router
from services.platega_cron import platega_pending_payment_loop

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не найден в .env")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

for router in (
    start_router,
    trial_router,
    payments_router,
    help_router,
    keys_router,
    invite_router,
    services_router,
    admin_router,
):
    dp.include_router(router)


async def reminder_loop():
    await keys_reminder_loop(bot)


async def main():
    logger.info("Starting VPN bot")
    init_db()
    logger.info("Database initialized")
    reminder_task = asyncio.create_task(reminder_loop())
    platega_task = asyncio.create_task(platega_pending_payment_loop())
    await bot.delete_webhook(drop_pending_updates=False)
    logger.info("Webhook cleared, polling started")
    try:
        await dp.start_polling(bot)
    finally:
        for task in (reminder_task, platega_task):
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception:
        logger.exception("Bot stopped because of an unhandled error")
        raise
