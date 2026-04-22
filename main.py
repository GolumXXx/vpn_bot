import asyncio

from aiogram import Bot, Dispatcher

from config import BOT_TOKEN
from database.db import init_db
from routers.start import router as start_router
from routers.trial import router as trial_router
from routers.payments import router as payments_router
from routers.help import router as help_router
from routers.keys import router as keys_router
from routers.invite import router as invite_router
from routers.services import router as services_router

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
):
    dp.include_router(router)


async def main():
    init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())