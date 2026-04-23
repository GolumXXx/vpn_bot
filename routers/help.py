from aiogram import Router, F
from aiogram.types import CallbackQuery

from keyboards import help_menu
from routers.ui import safe_edit_text

router = Router()


@router.callback_query(F.data == "help")
async def help_handler(callback: CallbackQuery):
    await safe_edit_text(
        callback.message,
        "🛟 Поддержка\n\n"
        "Если что-то не получается, напиши в поддержку.\n\n"
        "Мы поможем с подключением и оплатой.",
        reply_markup=help_menu
    )
    await callback.answer()
