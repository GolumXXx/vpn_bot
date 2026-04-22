from aiogram import Router, F
from aiogram.types import CallbackQuery

from config import BOT_USERNAME
from keyboards import invite_menu
from routers.ui import safe_edit_text

router = Router()


@router.callback_query(F.data == "invite")
async def invite_handler(callback: CallbackQuery):
    await safe_edit_text(
        callback.message,
        "🎁 Пригласить друга\n\n"
        "Здесь позже будет реферальная система.\n\n"
        "Пока можно сделать заглушку с приглашением.",
        reply_markup=invite_menu
    )
    await callback.answer()


@router.callback_query(F.data == "get_invite_link")
async def get_invite_link_handler(callback: CallbackQuery):
    user_id = callback.from_user.id
    invite_link = f"https://t.me/{BOT_USERNAME}?start=ref_{user_id}"

    await callback.answer()
    await callback.message.answer(
        f"🔗 Твоя пригласительная ссылка:\n\n{invite_link}\n\n"
        "Позже сюда добавим учёт приглашённых пользователей."
    )
