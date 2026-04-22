from aiogram import F, Router
from aiogram.types import CallbackQuery

from database.db import (
    add_or_update_user,
    create_paid_key,
    extend_key,
    get_latest_paid_key_by_tariff,
)
from keyboards import get_payment_menu, main_inline_menu, renew_menu
from routers.ui import safe_edit_text
from services.xui_client import XUIError


router = Router()

TARIFFS = {
    "1m": {"name": "VPN на 1 месяц", "days": 30, "price": 199, "label": "1 месяц"},
    "3m": {"name": "VPN на 3 месяца", "days": 90, "price": 499, "label": "3 месяца"},
    "12m": {"name": "VPN на 12 месяцев", "days": 365, "price": 1490, "label": "12 месяцев"},
}

RENEW_TEXT = (
    "💳 Продление VPN\n\n"
    "Выбери срок подписки:"
)


def build_tariff_text(tariff_code: str) -> str | None:
    tariff = TARIFFS.get(tariff_code)
    if not tariff:
        return None

    return (
        "💳 Оформление подписки\n\n"
        f"Срок: {tariff['label']}\n"
        f"Стоимость: {tariff['price']} ₽\n\n"
        "Если такой ключ уже есть, бот продлит его без дубликата."
    )


@router.callback_query(F.data == "renew_sub")
async def renew_sub_handler(callback: CallbackQuery):
    await safe_edit_text(
        callback.message,
        RENEW_TEXT,
        reply_markup=renew_menu,
    )
    await callback.answer()


@router.callback_query(F.data == "payments_back_main")
async def payments_back_main_handler(callback: CallbackQuery):
    await safe_edit_text(
        callback.message,
        "Главное меню 👇",
        reply_markup=main_inline_menu,
    )
    await callback.answer()


@router.callback_query(F.data == "back_renew")
async def back_renew_handler(callback: CallbackQuery):
    await safe_edit_text(
        callback.message,
        RENEW_TEXT,
        reply_markup=renew_menu,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("tariff_"))
async def tariff_handler(callback: CallbackQuery):
    tariff_code = callback.data.removeprefix("tariff_")
    text = build_tariff_text(tariff_code)

    if text is None:
        await callback.answer("Тариф не найден", show_alert=True)
        return

    await safe_edit_text(
        callback.message,
        text,
        reply_markup=get_payment_menu(tariff_code),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("pay_"))
async def process_payment(callback: CallbackQuery):
    tariff_code = callback.data.removeprefix("pay_")
    tariff = TARIFFS.get(tariff_code)
    if not tariff:
        await callback.answer("Тариф не найден", show_alert=True)
        return

    user = callback.from_user
    add_or_update_user(
        telegram_id=user.id,
        username=user.username,
        first_name=user.first_name,
    )

    existing_key = get_latest_paid_key_by_tariff(user.id, tariff["name"])

    try:
        if existing_key:
            new_expires = extend_key(existing_key["id"], tariff["days"])

            await callback.answer("Подписка продлена ✅", show_alert=True)
            await callback.message.answer(
                "✅ Подписка продлена\n\n"
                "Твой VPN-ключ обновлён.\n"
                f"Новая дата окончания: {new_expires}"
            )
            return

        key = await create_paid_key(
            telegram_id=user.id,
            tariff_name=tariff["name"],
            duration_days=tariff["days"],
            username=user.username,
            first_name=user.first_name,
            traffic_limit_gb=0,
        )

        await callback.answer("Подписка оформлена ✅", show_alert=True)
        await callback.message.answer(
            "✅ Подписка оформлена\n\n"
            f"Тариф: {tariff['label']}\n"
            "VPN-ключ доступен в разделе «Мои активные ключи»."


        )
    except XUIError as error:
        await callback.message.answer(
            "Не удалось выдать VPN-ключ.\n"
            "Попробуй ещё раз позже или обратись в поддержку."
        )
    except Exception as error:
        await callback.message.answer(
            "Не удалось оформить подписку.\n"
            f"Ошибка: {error}"
        )
