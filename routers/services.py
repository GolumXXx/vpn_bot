from aiogram import Router, F
from aiogram.types import CallbackQuery

from keyboards import services_menu
from routers.ui import safe_edit_text

router = Router()


@router.callback_query(F.data == "services")
async def services_handler(callback: CallbackQuery):
    await safe_edit_text(
        callback.message,
        "🌐 VPN\n\n"
        "Подключайся и управляй доступом прямо в боте.",
        reply_markup=services_menu
    )
    await callback.answer()


@router.callback_query(F.data == "service_vpn")
async def service_vpn_handler(callback: CallbackQuery):
    await safe_edit_text(
        callback.message,
        "🌐 VPN\n\n"
        "Выбери «Мои активные ключи», чтобы подключиться.",
        reply_markup=services_menu
    )
    await callback.answer()
