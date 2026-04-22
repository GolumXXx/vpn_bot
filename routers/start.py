from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery

from database.db import add_or_update_user
from keyboards import reply_menu, main_inline_menu
from routers.ui import safe_edit_text

router = Router()


WELCOME_TEXT = (
    "Привет 👋\n\n"
    "Здесь можно управлять VPN-ключами, продлевать подписку "
    "и получать пробный доступ."
)

MAIN_MENU_TEXT = (
    "🏠 Главное меню\n\n"
    "Выбери нужный раздел:"
)


async def send_main_menu(message: Message):
    await message.answer(
        WELCOME_TEXT,
        reply_markup=reply_menu
    )

    await message.answer(
        MAIN_MENU_TEXT,
        reply_markup=main_inline_menu
    )


@router.message(CommandStart())
async def start_handler(message: Message):
    user = message.from_user

    add_or_update_user(
        telegram_id=user.id,
        username=user.username,
        first_name=user.first_name,
    )

    await send_main_menu(message)


@router.message(F.text == "Главное меню")
async def menu_handler(message: Message):
    user = message.from_user

    add_or_update_user(
        telegram_id=user.id,
        username=user.username,
        first_name=user.first_name,
    )

    await message.answer(
        MAIN_MENU_TEXT,
        reply_markup=main_inline_menu
    )


@router.callback_query(F.data == "back_main")
async def back_main_handler(callback: CallbackQuery):
    await safe_edit_text(
        callback.message,
        MAIN_MENU_TEXT,
        reply_markup=main_inline_menu
    )
    await callback.answer()
