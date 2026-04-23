import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from config import ADMIN_IDS
from database.db import (
    MANUAL_PAYMENT_STATUS_APPROVED,
    MANUAL_PAYMENT_STATUS_PENDING,
    MANUAL_PAYMENT_STATUS_PROCESSING,
    MANUAL_PAYMENT_STATUS_RECEIPT_UPLOADED,
    MANUAL_PAYMENT_STATUS_REPLACED,
    add_or_update_user,
    attach_manual_payment_receipt,
    create_manual_payment,
    create_paid_key,
    extend_key,
    get_latest_open_manual_payment,
    get_latest_paid_key_by_tariff,
    get_manual_payment_by_order_id,
    get_user,
    mark_manual_payment_approved,
    reopen_manual_payment,
    start_manual_payment_processing,
)
from keyboards import (
    get_manual_payment_admin_menu,
    get_payment_menu,
    main_inline_menu,
    manual_payment_wait_menu,
    payment_done_menu,
    renew_menu,
)
from routers.ui import safe_edit_text
from services.xui_client import XUIError


router = Router()
logger = logging.getLogger(__name__)
ADMIN_ID_SET = set(ADMIN_IDS)

TARIFFS = {
    "1m": {"name": "VPN на 1 месяц", "days": 30, "price": 199, "label": "1 месяц"},
    "3m": {"name": "VPN на 3 месяца", "days": 90, "price": 499, "label": "3 месяца"},
    "12m": {"name": "VPN на 12 месяцев", "days": 365, "price": 1490, "label": "12 месяцев"},
}

RENEW_TEXT = (
    "💳 Купить / продлить VPN\n\n"
    "Выбери срок доступа:"
)

MAIN_MENU_TEXT = (
    "🚀 GolumVPN — интернет без тормозов и ограничений\n\n"
    "«Моя прелесть…» — это уже не кольцо,\n"
    "а твой стабильный интернет 😎\n\n"
    "😤 Забудь про:\n"
    "📶 зависающие видео\n"
    "💌 пропущенные сообщения\n"
    "▶️ навязчивую рекламу\n"
    "📵 блокировки и ограничения\n\n"
    "🔑 Попробуй бесплатно или оформи доступ\n"
    "👇 Выбери, что хочешь сделать:"
)

GENERIC_ERROR_TEXT = (
    "Что-то пошло не так 😕\n\n"
    "Попробуй ещё раз или обратись в поддержку."
)

VPN_KEY_ERROR_TEXT = (
    "Не удалось выдать VPN-ключ\n\n"
    "Попробуй ещё раз позже или обратись в поддержку."
)

MANUAL_PAYMENT_UNAVAILABLE_TEXT = (
    "Ручная оплата временно недоступна.\n\n"
    "Напиши в поддержку."
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
        "💳 Оформление VPN\n\n"
        f"Срок: {tariff['label']}\n"
        f"Стоимость: {tariff['price']} ₽\n\n"
        "Нажми «Оплатить по чеку», чтобы продолжить."
    )


def build_manual_payment_text(payment, tariff: dict) -> str:
    return (
        "🧾 Заявка создана\n\n"
        f"Твой ID оплаты: {row_get(payment, 'order_id', '—')}\n"
        f"Тариф: {tariff['label']} — {tariff['price']} ₽\n\n"
        "Оплати и отправь фото чека в этот чат."
    )


def build_admin_receipt_text(payment, tariff: dict, user) -> str:
    username = getattr(user, "username", None)
    first_name = getattr(user, "first_name", None) or "—"
    username_text = f"@{username}" if username else "—"

    return (
        "🧾 Новый чек\n\n"
        f"ID оплаты: {row_get(payment, 'order_id', '—')}\n"
        f"Тариф: {tariff['label']} — {tariff['price']} ₽\n"
        f"Пользователь ID: {row_get(payment, 'telegram_id', '—')}\n"
        f"Логин: {username_text}\n"
        f"Имя: {first_name}"
    )


def build_user_payment_success_text(tariff: dict, result: dict) -> str:
    if result["action"] == "extended":
        return (
            "Оплата подтверждена ✅\n\n"
            f"Тариф: {tariff['label']}\n"
            "Подписка продлена.\n"
            f"Действует до: {result['expires_at']}\n\n"
            "VPN уже готов к использованию 🚀"
        )

    return (
        "Оплата подтверждена ✅\n\n"
        f"Тариф: {tariff['label']}\n"
        "VPN уже готов к использованию 🚀"
    )


def build_admin_payment_success_text(payment, tariff: dict, result: dict) -> str:
    if result["action"] == "extended":
        action_text = f"Подписка продлена до {result['expires_at']}"
    else:
        action_text = "Новый VPN-ключ выдан"

    return (
        "Оплата подтверждена ✅\n\n"
        f"ID оплаты: {row_get(payment, 'order_id', '—')}\n"
        f"Тариф: {tariff['label']}\n"
        f"User ID: {row_get(payment, 'telegram_id', '—')}\n"
        f"{action_text}"
    )


def get_manual_payment_status_alert(status: str | None) -> str:
    if status == MANUAL_PAYMENT_STATUS_PENDING:
        return "Чек ещё не получен"
    if status == MANUAL_PAYMENT_STATUS_PROCESSING:
        return "Эта заявка уже обрабатывается"
    if status == MANUAL_PAYMENT_STATUS_APPROVED:
        return "Оплата уже подтверждена"
    if status == MANUAL_PAYMENT_STATUS_REPLACED:
        return "Заявка уже заменена новой"
    return "Заявка недоступна"


async def fulfill_paid_order(
    telegram_id: int,
    tariff_code: str,
    username: str | None = None,
    first_name: str | None = None,
) -> dict:
    tariff = TARIFFS.get(tariff_code)
    if not tariff:
        raise ValueError(f"Unknown tariff code: {tariff_code}")

    add_or_update_user(
        telegram_id=telegram_id,
        username=username,
        first_name=first_name,
    )

    existing_key = get_latest_paid_key_by_tariff(telegram_id, tariff["name"])
    if existing_key:
        key_id = row_get(existing_key, "id")
        if not key_id:
            raise ValueError(f"Cannot extend key without id for user {telegram_id}")

        new_expires = extend_key(key_id, tariff["days"])
        logger.info(
            "Extended paid VPN key after manual confirmation: user_id=%s tariff=%s key_id=%s expires_at=%s",
            telegram_id,
            tariff_code,
            key_id,
            new_expires,
        )
        return {
            "action": "extended",
            "expires_at": new_expires,
            "tariff": tariff,
        }

    await create_paid_key(
        telegram_id=telegram_id,
        tariff_name=tariff["name"],
        duration_days=tariff["days"],
        username=username,
        first_name=first_name,
        traffic_limit_gb=0,
    )
    logger.info(
        "Created paid VPN key after manual confirmation: user_id=%s tariff=%s days=%s",
        telegram_id,
        tariff_code,
        tariff["days"],
    )
    return {
        "action": "created",
        "expires_at": None,
        "tariff": tariff,
    }


async def send_receipt_to_admins(message: Message, payment, tariff: dict) -> int:
    order_id = row_get(payment, "order_id")
    if not order_id or not message.photo:
        return 0

    sent_count = 0
    photo = message.photo[-1]
    caption = build_admin_receipt_text(payment, tariff, message.from_user)

    for admin_id in ADMIN_ID_SET:
        try:
            await message.bot.send_photo(
                chat_id=admin_id,
                photo=photo.file_id,
                caption=caption,
                reply_markup=get_manual_payment_admin_menu(order_id),
            )
            sent_count += 1
        except Exception:
            logger.exception(
                "Failed to send manual payment receipt to admin: order_id=%s admin_id=%s user_id=%s",
                order_id,
                admin_id,
                message.from_user.id,
            )

    return sent_count


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
    if not ADMIN_ID_SET:
        logger.error("Manual payment requested but ADMIN_IDS are not configured")
        await callback.answer(MANUAL_PAYMENT_UNAVAILABLE_TEXT, show_alert=True)
        return

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
        payment = create_manual_payment(
            telegram_id=user.id,
            tariff_code=tariff_code,
        )
        logger.info(
            "Created manual payment request: order_id=%s user_id=%s tariff=%s",
            row_get(payment, "order_id"),
            user.id,
            tariff_code,
        )

        await safe_edit_text(
            callback.message,
            build_manual_payment_text(payment, tariff),
            reply_markup=manual_payment_wait_menu,
        )
        await callback.answer("Заявка создана ✅", show_alert=True)
    except Exception:
        logger.exception(
            "Unexpected manual payment request error: user_id=%s tariff=%s",
            user.id,
            tariff_code,
        )
        await callback.message.answer(GENERIC_ERROR_TEXT)


@router.message(F.photo)
async def receipt_photo_handler(message: Message):
    payment = get_latest_open_manual_payment(message.from_user.id)
    if not payment or not message.photo:
        return

    order_id = row_get(payment, "order_id")
    tariff_code = row_get(payment, "tariff_code")
    tariff = TARIFFS.get(tariff_code)

    if not order_id or not tariff:
        logger.error(
            "Invalid manual payment before receipt handling: order_id=%s user_id=%s tariff=%s",
            order_id,
            message.from_user.id,
            tariff_code,
        )
        await message.answer(GENERIC_ERROR_TEXT)
        return

    photo = message.photo[-1]

    try:
        attach_manual_payment_receipt(
            order_id=order_id,
            receipt_file_id=photo.file_id,
            receipt_unique_id=photo.file_unique_id,
            user_message_id=message.message_id,
        )
        logger.info(
            "Received manual payment receipt: order_id=%s user_id=%s tariff=%s",
            order_id,
            message.from_user.id,
            tariff_code,
        )

        delivered_to = await send_receipt_to_admins(message, payment, tariff)
        if delivered_to == 0:
            await message.answer(
                "Чек получен ✅\n\n"
                "Не удалось отправить админу.\n"
                "Попробуй ещё раз позже."
            )
            return

        await message.answer(
            "Чек получен ✅\n\n"
            "Ожидай подтверждения."
        )
    except Exception:
        logger.exception(
            "Unexpected manual receipt processing error: order_id=%s user_id=%s",
            order_id,
            message.from_user.id,
        )
        await message.answer(GENERIC_ERROR_TEXT)


@router.callback_query(F.data.startswith("approve_manual_payment:"))
async def approve_manual_payment_handler(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_ID_SET:
        await callback.answer("Нет доступа", show_alert=True)
        return

    try:
        order_id = callback.data.split(":", maxsplit=1)[1].strip()
    except (AttributeError, IndexError):
        logger.warning("Invalid manual payment approval callback: data=%s user_id=%s", callback.data, callback.from_user.id)
        await callback.answer(GENERIC_ERROR_TEXT, show_alert=True)
        return

    payment = get_manual_payment_by_order_id(order_id)
    if not payment:
        await callback.answer("Заявка не найдена", show_alert=True)
        return

    status = row_get(payment, "status")
    if status != MANUAL_PAYMENT_STATUS_RECEIPT_UPLOADED:
        await callback.answer(get_manual_payment_status_alert(status), show_alert=True)
        return

    if not start_manual_payment_processing(order_id, callback.from_user.id):
        payment = get_manual_payment_by_order_id(order_id)
        await callback.answer(
            get_manual_payment_status_alert(row_get(payment, "status")),
            show_alert=True,
        )
        return

    telegram_id = row_get(payment, "telegram_id")
    tariff_code = row_get(payment, "tariff_code")
    tariff = TARIFFS.get(tariff_code)
    user = get_user(telegram_id) if telegram_id else None

    try:
        if not telegram_id or not tariff:
            raise ValueError(f"Invalid manual payment payload: order_id={order_id}")

        result = await fulfill_paid_order(
            telegram_id=telegram_id,
            tariff_code=tariff_code,
            username=row_get(user, "username"),
            first_name=row_get(user, "first_name"),
        )
        mark_manual_payment_approved(order_id, callback.from_user.id)
    except XUIError:
        reopen_manual_payment(order_id)
        logger.exception(
            "XUI error during manual payment approval: order_id=%s admin_id=%s user_id=%s",
            order_id,
            callback.from_user.id,
            telegram_id,
        )
        await callback.answer(VPN_KEY_ERROR_TEXT, show_alert=True)
        await callback.message.answer(
            "Не удалось выдать VPN-ключ.\n"
            f"ID оплаты: {order_id}"
        )
        return
    except Exception:
        reopen_manual_payment(order_id)
        logger.exception(
            "Unexpected manual payment approval error: order_id=%s admin_id=%s user_id=%s",
            order_id,
            callback.from_user.id,
            telegram_id,
        )
        await callback.answer(GENERIC_ERROR_TEXT, show_alert=True)
        await callback.message.answer(
            "Не удалось обработать заявку.\n"
            f"ID оплаты: {order_id}"
        )
        return

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        logger.exception(
            "Failed to clear manual payment approval markup: order_id=%s admin_id=%s",
            order_id,
            callback.from_user.id,
        )

    await callback.answer("Оплата подтверждена ✅", show_alert=True)
    await callback.message.answer(build_admin_payment_success_text(payment, tariff, result))

    try:
        await callback.bot.send_message(
            chat_id=telegram_id,
            text=build_user_payment_success_text(tariff, result),
            reply_markup=payment_done_menu,
        )
    except Exception:
        logger.exception(
            "Failed to notify user about approved manual payment: order_id=%s user_id=%s",
            order_id,
            telegram_id,
        )
