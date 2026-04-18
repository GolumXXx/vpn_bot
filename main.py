import asyncio
import os


from aiogram import Bot, Dispatcher
from aiogram.types import Message
from dotenv import load_dotenv

load_dotenv()

token = os.getenv("BOT_TOKEN")
if not token:
    raise ValueError("BOT_TOKEN не найден в .env")


bot = Bot(token=token)
dp = Dispatcher()

@dp.message()
async def echo(message: Message):
    await message.answer(message.text or "Я получил сообщение")


async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())

