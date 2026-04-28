from aiogram import Router, F
from aiogram.types import CallbackQuery

from keyboards import help_menu
from utils.telegram import safe_edit_text

router = Router()


@router.callback_query(F.data == "help")
async def help_handler(callback: CallbackQuery):
    await safe_edit_text(
        callback.message,
        "🛟 Поддержка GolumVPN\n\n"
        "Мы рядом, если что-то пошло не так.\n\n"
        "🔧 Поможем:\n"
        "• подключить VPN\n"
        "• проверить оплату\n"
        "• восстановить доступ\n"
        "• разобраться с приложением\n\n"
        "📱 Быстрый старт:\n"
        "1. Открой «Мои VPN-ключи»\n"
        "2. Нажми «Подключить VPN»\n"
        "3. Выбери своё устройство\n"
        "4. Следуй инструкции\n\n"
        "📄 Документы:\n"
        "Пользовательское соглашение и политика конфиденциальности "
        "доступны по кнопкам ниже.\n\n"
        "👇 Выбери нужное действие:",
        reply_markup=help_menu
    )
    await callback.answer()
