from aiogram import Router, F
from aiogram.types import CallbackQuery

from keyboards import help_menu
from routers.ui import safe_edit_text

router = Router()


@router.callback_query(F.data == "help")
async def help_handler(callback: CallbackQuery):
    await safe_edit_text(
        callback.message,
        "🛟 Помощь\n\n"
        "Если у тебя появились вопросы по подключению, оплате или работе VPN,\n"
        "ты можешь написать в поддержку.\n\n"
        "Нажми кнопку ниже:",
        reply_markup=help_menu
    )
    await callback.answer()
