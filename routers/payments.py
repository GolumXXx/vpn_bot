import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery

from database.db import (
    add_or_update_user,
    create_paid_key,
    extend_key,
    get_latest_paid_key_by_tariff,
)
from keyboards import get_payment_menu, main_inline_menu, payment_done_menu, renew_menu
from routers.ui import safe_edit_text
from services.xui_client import XUIError


router = Router()
logger = logging.getLogger(__name__)

TARIFFS = {
    "1m": {"name": "VPN на 1 месяц", "days": 30, "price": 199, "label": "1 месяц"},
    "3m": {"name": "VPN на 3 месяца", "days": 90, "price": 499, "label": "3 месяца"},
    "12m": {"name": "VPN на 12 месяцев", "days": 365, "price": 1490, "label": "12 месяцев"},
}

RENEW_TEXT = (
    "💳 Продление VPN\n\n"
    "Выбери срок подписки:"
)

MAIN_MENU_TEXT = (
    "🏠 Главное меню\n\n"
    "Что хочешь сделать?"
)

GENERIC_ERROR_TEXT = (
    "Что-то пошло не так 😕\n\n"
    "Попробуй ещё раз или обратись в поддержку."
)

VPN_KEY_ERROR_TEXT = (
    "Не удалось выдать VPN-ключ\n\n"
    "Попробуй ещё раз позже или обратись в поддержку."
)


def row_get(row, field, default=None):
    if not row:
        return default

    try:
        value = row[field]
    except (IndexError, KeyError, TypeError):
        return default

    return value if value is not None else default


def build_tariff_text(tariff_code: str) -> str | None:
    tariff = TARIFFS.get(tariff_code)
    if not tariff:
        return None

    return (
        "💳 Оформление подписки\n\n"
        f"Срок: {tariff['label']}\n"
        f"Стоимость: {tariff['price']} ₽\n\n"
        "Нажми «Оплатить», чтобы продолжить."
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
        MAIN_MENU_TEXT,
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
        logger.warning("Unknown tariff selected: tariff_code=%s user_id=%s", tariff_code, callback.from_user.id)
        await callback.answer("Не удалось найти тариф. Выбери срок ещё раз.", show_alert=True)
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
        logger.warning("Unknown payment tariff: tariff_code=%s user_id=%s", tariff_code, callback.from_user.id)
        await callback.answer("Не удалось найти тариф. Выбери срок ещё раз.", show_alert=True)
        return

    user = callback.from_user

    try:
        add_or_update_user(
            telegram_id=user.id,
            username=user.username,
            first_name=user.first_name,
        )

        existing_key = get_latest_paid_key_by_tariff(user.id, tariff["name"])

        if existing_key:
            key_id = row_get(existing_key, "id")
            if not key_id:
                logger.error(
                    "Cannot extend paid key without id: user_id=%s tariff=%s",
                    user.id,
                    tariff_code,
                )
                await callback.message.answer(GENERIC_ERROR_TEXT)
                return

            new_expires = extend_key(key_id, tariff["days"])
            logger.info(
                "Extended paid VPN key: user_id=%s tariff=%s key_id=%s expires_at=%s",
                user.id,
                tariff_code,
                key_id,
                new_expires,
            )

            await callback.answer("Подписка продлена ✅", show_alert=True)
            await callback.message.answer(
                "✅ Подписка продлена\n\n"
                "Твой VPN-ключ обновлён.\n"
                f"Новая дата окончания: {new_expires}",
                reply_markup=payment_done_menu,
            )
            return

        await create_paid_key(
            telegram_id=user.id,
            tariff_name=tariff["name"],
            duration_days=tariff["days"],
            username=user.username,
            first_name=user.first_name,
            traffic_limit_gb=0,
        )
        logger.info(
            "Created paid VPN key: user_id=%s tariff=%s days=%s",
            user.id,
            tariff_code,
            tariff["days"],
        )

        await callback.answer("Подписка оформлена ✅", show_alert=True)
        await callback.message.answer(
            "✅ Подписка оформлена\n\n"
            f"Тариф: {tariff['label']}\n"
            "VPN уже готов к использованию 🚀",
            reply_markup=payment_done_menu,
        )
    except XUIError:
        logger.exception(
            "XUI error during payment processing: user_id=%s tariff=%s",
            user.id,
            tariff_code,
        )
        await callback.message.answer(VPN_KEY_ERROR_TEXT)
    except Exception:
        logger.exception(
            "Unexpected payment processing error: user_id=%s tariff=%s",
            user.id,
            tariff_code,
        )
        await callback.message.answer(GENERIC_ERROR_TEXT)
