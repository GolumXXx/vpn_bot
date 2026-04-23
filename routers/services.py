from aiogram import Router, F
from aiogram.types import CallbackQuery

from keyboards import services_menu
from routers.keys import render_keys_list
from routers.ui import safe_edit_text

router = Router()


@router.callback_query(F.data == "services")
async def services_handler(callback: CallbackQuery):
    await safe_edit_text(
        callback.message,
        "📱 Как подключить VPN\n\n"
        "1. Открой «Мои VPN-ключи».\n"
        "2. Нажми «Подключить VPN».\n"
        "3. Выбери своё устройство и следуй шагам.\n\n"
        "Если ключа ещё нет, сначала возьми пробный доступ "
        "или оформи подписку.",
        reply_markup=services_menu
    )
    await callback.answer()


@router.callback_query(F.data == "service_vpn")
async def service_vpn_handler(callback: CallbackQuery):
    await render_keys_list(callback)
