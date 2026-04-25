import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from config import (
    ADMIN_IDS,
    MANUAL_PAYMENT_URL,
    PAYMENT_URL_1M,
    PAYMENT_URL_3M,
    PAYMENT_URL_6M,
)
from database.db import (
    MANUAL_PAYMENT_STATUS_APPROVED,
    MANUAL_PAYMENT_STATUS_CANCELLED,
    MANUAL_PAYMENT_STATUS_PENDING,
    MANUAL_PAYMENT_STATUS_PROCESSING,
    MANUAL_PAYMENT_STATUS_RECEIPT_UPLOADED,
    MANUAL_PAYMENT_STATUS_REPLACED,
    MANUAL_PAYMENT_STATUS_WAITING_ADMIN,
    add_bot_log,
    add_or_update_user,
    attach_manual_payment_receipt,
    cancel_pending_manual_payment,
    create_manual_payment,
    create_paid_key,
    extend_key,
    get_latest_open_manual_payment,
    get_latest_paid_key_by_tariff,
    get_manual_payment_by_order_id,
    get_user,
    get_user_keys,
    mark_manual_payment_waiting_admin,
    mark_manual_payment_approved,
    reopen_manual_payment,
    reset_manual_payment_waiting_admin,
    start_manual_payment_processing,
)
from keyboards import (
    get_main_inline_menu,
    get_manual_payment_admin_menu,
    get_manual_payment_request_menu,
    get_manual_payment_waiting_menu,
    get_payment_menu,
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
    "1m": {"name": "VPN на 1 месяц", "days": 30, "price": 89, "label": "1 месяц"},
    "3m": {"name": "VPN на 3 месяца", "days": 90, "price": 269, "label": "3 месяца"},
    "6m": {"name": "VPN на 6 месяцев", "days": 180, "price": 549, "label": "6 месяцев"},
}
PAYMENT_URLS = {
    "1m": PAYMENT_URL_1M or MANUAL_PAYMENT_URL,
    "3m": PAYMENT_URL_3M or MANUAL_PAYMENT_URL,
    "6m": PAYMENT_URL_6M or MANUAL_PAYMENT_URL,
}

RENEW_TEXT = (
    "💳 Купить / продлить VPN\n\n"
    "Выбери срок доступа:"
)

MAIN_MENU_TEXT = (
    "🚀 GolumVPN — быстрый и стабильный интернет\n\n"
    "«Моя прелесть…» — это уже не кольцо,\n"
    "а твой стабильный интернет 😎\n\n"
    "😤 Забудь про:\n"
    "📶 зависающие видео\n"
    "💌 пропущенные сообщения\n"
    "▶️ навязчивую рекламу\n\n"
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
        "Нажми «Создать заявку», чтобы продолжить."
    )


def get_tariff_payment_url(tariff_code: str) -> str | None:
    return PAYMENT_URLS.get(tariff_code)


def build_manual_payment_text(payment, tariff: dict, payment_url: str | None = None) -> str:
    lines = [
        "🧾 Заявка создана",
        "",
        f"Твой ID оплаты: {row_get(payment, 'order_id', '—')}",
        f"Тариф: {tariff['label']}",
        f"Стоимость: {tariff['price']} ₽",
        "",
    ]

    if payment_url:
        lines.extend(
            [
                "1. Нажми кнопку ниже и оплати через Ozon",
                "2. После оплаты отправь чек в этот чат",
            ]
        )
    else:
        lines.extend(
            [
                "1. Оплати доступ",
                "2. После оплаты отправь чек в этот чат",
            ]
        )

    return "\n".join(lines)


def build_manual_payment_waiting_text(payment, tariff: dict) -> str:
    return (
        "⏳ Заявка отправлена на проверку\n\n"
        f"Твой ID оплаты: {row_get(payment, 'order_id', '—')}\n"
        f"Тариф: {tariff['label']}\n"
        f"Стоимость: {tariff['price']} ₽"
    )


def build_receipt_received_text() -> str:
    return (
        "✅ Чек получен\n\n"
        "Заявка отправлена на проверку"
    )


def build_admin_receipt_text(payment, tariff: dict, user) -> str:
    username = getattr(user, "username", None)
    first_name = getattr(user, "first_name", None) or "—"
    username_text = f"@{username}" if username else "—"

    return (
        "🧾 Оплата на проверку\n\n"
        f"ID оплаты: {row_get(payment, 'order_id', '—')}\n"
        f"Тариф: {tariff['label']} — {tariff['price']} ₽\n"
        f"Пользователь ID: {row_get(payment, 'telegram_id', '—')}\n"
        f"Логин: {username_text}\n"
        f"Имя: {first_name}\n\n"
        "Пользователь отправил чек."
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
    if status == MANUAL_PAYMENT_STATUS_RECEIPT_UPLOADED:
        return "Чек получен, заявка ещё не отправлена админу"
    if status == MANUAL_PAYMENT_STATUS_PROCESSING:
        return "Эта заявка уже обрабатывается"
    if status == MANUAL_PAYMENT_STATUS_APPROVED:
        return "Оплата уже подтверждена"
    if status == MANUAL_PAYMENT_STATUS_REPLACED:
        return "Заявка уже заменена новой"
    if status == MANUAL_PAYMENT_STATUS_CANCELLED:
        return "Заявка отменена"
    return "Заявка недоступна"


def get_user_manual_payment_status_alert(status: str | None) -> str:
    if status == MANUAL_PAYMENT_STATUS_PENDING:
        return "Сначала отправь чек в этот чат 🧾"
    if status == MANUAL_PAYMENT_STATUS_WAITING_ADMIN:
        return "⏳ Заявка уже отправлена на проверку"
    if status == MANUAL_PAYMENT_STATUS_RECEIPT_UPLOADED:
        return "✅ Чек получен. Заявка отправляется на проверку"
    if status == MANUAL_PAYMENT_STATUS_PROCESSING:
        return "Оплата уже проверяется"
    if status == MANUAL_PAYMENT_STATUS_APPROVED:
        return "Оплата уже подтверждена ✅"
    if status == MANUAL_PAYMENT_STATUS_REPLACED:
        return "Заявка уже заменена новой"
    if status == MANUAL_PAYMENT_STATUS_CANCELLED:
        return "❌ Заявка отменена"
    return "Заявка недоступна"


async def fulfill_paid_order(
    telegram_id: int,
    tariff_code: str,
    username: str | None = None,
    first_name: str | None = None,
    order_id: str | None = None,
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
        add_bot_log(
            "paid_key_extended",
            telegram_id=telegram_id,
            username=username,
            key_id=key_id,
            order_id=order_id,
            message=f"Платный ключ продлён: тариф={tariff_code}, до={new_expires}",
        )
        return {
            "action": "extended",
            "expires_at": new_expires,
            "tariff": tariff,
            "key_id": key_id,
        }

    await create_paid_key(
        telegram_id=telegram_id,
        tariff_name=tariff["name"],
        duration_days=tariff["days"],
        username=username,
        first_name=first_name,
        traffic_limit_gb=0,
    )
    keys = get_user_keys(telegram_id)
    key_id = row_get(keys[0], "id") if keys else None
    logger.info(
        "Created paid VPN key after manual confirmation: user_id=%s tariff=%s days=%s",
        telegram_id,
        tariff_code,
        tariff["days"],
    )
    add_bot_log(
        "paid_key_created",
        telegram_id=telegram_id,
        username=username,
        key_id=key_id,
        order_id=order_id,
        message=f"Платный ключ создан: тариф={tariff_code}, дней={tariff['days']}",
    )
    return {
        "action": "created",
        "expires_at": None,
        "tariff": tariff,
        "key_id": key_id,
    }


async def send_receipt_to_admins(bot, user, payment, tariff: dict) -> int:
    order_id = row_get(payment, "order_id")
    receipt_file_id = row_get(payment, "receipt_file_id")
    if not order_id or not receipt_file_id:
        return 0

    sent_count = 0
    caption = build_admin_receipt_text(payment, tariff, user)

    for admin_id in ADMIN_ID_SET:
        try:
            await bot.send_photo(
                chat_id=admin_id,
                photo=receipt_file_id,
                caption=caption,
                reply_markup=get_manual_payment_admin_menu(order_id),
            )
            sent_count += 1
        except Exception:
            logger.exception(
                "Failed to send manual payment receipt to admin: order_id=%s admin_id=%s user_id=%s",
                order_id,
                admin_id,
                getattr(user, "id", None),
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
        reply_markup=get_main_inline_menu(callback.from_user.id),
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
        add_bot_log(
            "payment_request_created",
            telegram_id=user.id,
            username=user.username,
            order_id=row_get(payment, "order_id"),
            message=f"Создана заявка на оплату: тариф={tariff_code}",
        )
        payment_url = get_tariff_payment_url(tariff_code)
        order_id = row_get(payment, "order_id")
        reply_markup = manual_payment_wait_menu

        if order_id:
            reply_markup = get_manual_payment_request_menu(order_id, payment_url)

        await safe_edit_text(
            callback.message,
            build_manual_payment_text(payment, tariff, payment_url),
            reply_markup=reply_markup,
        )
        await callback.answer("Заявка создана ✅", show_alert=True)
    except Exception:
        logger.exception(
            "Unexpected manual payment request error: user_id=%s tariff=%s",
            user.id,
            tariff_code,
        )
        await callback.message.answer(GENERIC_ERROR_TEXT)


@router.callback_query(F.data.startswith("cancel_manual_payment:"))
async def cancel_manual_payment_handler(callback: CallbackQuery):
    try:
        order_id = callback.data.split(":", maxsplit=1)[1].strip()
    except (AttributeError, IndexError):
        logger.warning(
            "Invalid manual payment cancel callback: data=%s user_id=%s",
            callback.data,
            callback.from_user.id,
        )
        await callback.answer(GENERIC_ERROR_TEXT, show_alert=True)
        return

    payment = get_manual_payment_by_order_id(order_id)
    if not payment or row_get(payment, "telegram_id") != callback.from_user.id:
        await callback.answer("Заявка не найдена", show_alert=True)
        return

    if row_get(payment, "status") != MANUAL_PAYMENT_STATUS_PENDING:
        await callback.answer(get_user_manual_payment_status_alert(row_get(payment, "status")), show_alert=True)
        return

    if not cancel_pending_manual_payment(order_id):
        payment = get_manual_payment_by_order_id(order_id)
        await callback.answer(get_user_manual_payment_status_alert(row_get(payment, "status")), show_alert=True)
        return

    add_bot_log(
        "payment_cancelled_user",
        telegram_id=callback.from_user.id,
        username=callback.from_user.username,
        order_id=order_id,
        message="Заявка отменена пользователем",
    )
    await safe_edit_text(callback.message, "❌ Заявка отменена")
    await callback.answer("Заявка отменена")


@router.callback_query(F.data.startswith("manual_payment_paid:"))
async def manual_payment_paid_handler(callback: CallbackQuery):
    try:
        order_id = callback.data.split(":", maxsplit=1)[1].strip()
    except (AttributeError, IndexError):
        logger.warning(
            "Invalid manual payment paid callback: data=%s user_id=%s",
            callback.data,
            callback.from_user.id,
        )
        await callback.answer(GENERIC_ERROR_TEXT, show_alert=True)
        return

    payment = get_manual_payment_by_order_id(order_id)
    if not payment or row_get(payment, "telegram_id") != callback.from_user.id:
        await callback.answer("Заявка не найдена", show_alert=True)
        return

    status = row_get(payment, "status")
    if status == MANUAL_PAYMENT_STATUS_PENDING or not row_get(payment, "receipt_file_id"):
        await callback.answer("Сначала отправь чек в этот чат 🧾", show_alert=True)
        return

    if status != MANUAL_PAYMENT_STATUS_RECEIPT_UPLOADED:
        await callback.answer(get_user_manual_payment_status_alert(status), show_alert=True)
        return

    tariff_code = row_get(payment, "tariff_code")
    tariff = TARIFFS.get(tariff_code)
    if not tariff:
        logger.error(
            "Invalid manual payment before user confirmation: order_id=%s user_id=%s tariff=%s",
            order_id,
            callback.from_user.id,
            tariff_code,
        )
        await callback.answer(GENERIC_ERROR_TEXT, show_alert=True)
        return

    if not mark_manual_payment_waiting_admin(order_id, user_message_id=callback.message.message_id):
        payment = get_manual_payment_by_order_id(order_id)
        await callback.answer(
            get_user_manual_payment_status_alert(row_get(payment, "status")),
            show_alert=True,
        )
        return

    delivered_to = await send_receipt_to_admins(
        callback.bot,
        callback.from_user,
        payment,
        tariff,
    )
    if delivered_to == 0:
        reset_manual_payment_waiting_admin(order_id)
        await callback.answer(
            "Не удалось отправить заявку админу. Попробуй ещё раз позже.",
            show_alert=True,
        )
        return

    logger.info(
        "User confirmed manual payment: order_id=%s user_id=%s tariff=%s admins=%s",
        order_id,
        callback.from_user.id,
        tariff_code,
        delivered_to,
    )

    await safe_edit_text(
        callback.message,
        build_manual_payment_waiting_text(payment, tariff),
        reply_markup=get_manual_payment_waiting_menu(get_tariff_payment_url(tariff_code)),
    )
    await callback.answer("⏳ Ожидаем подтверждения оплаты", show_alert=True)


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

        if not mark_manual_payment_waiting_admin(order_id, user_message_id=message.message_id):
            payment = get_manual_payment_by_order_id(order_id)
            await message.answer(get_user_manual_payment_status_alert(row_get(payment, "status")))
            return

        payment = get_manual_payment_by_order_id(order_id)
        delivered_to = await send_receipt_to_admins(
            message.bot,
            message.from_user,
            payment,
            tariff,
        )
        if delivered_to == 0:
            reset_manual_payment_waiting_admin(order_id)
            await message.answer(
                "✅ Чек получен\n\n"
                "Не удалось отправить заявку админу. Попробуй ещё раз позже."
            )
            return

        logger.info(
            "Received manual payment receipt and sent to admins: order_id=%s user_id=%s tariff=%s admins=%s",
            order_id,
            message.from_user.id,
            tariff_code,
            delivered_to,
        )
        add_bot_log(
            "payment_receipt_sent",
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            order_id=order_id,
            message=f"Чек отправлен админам: тариф={tariff_code}, admins={delivered_to}",
        )

        await message.answer(build_receipt_received_text())
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
    if status not in {MANUAL_PAYMENT_STATUS_RECEIPT_UPLOADED, MANUAL_PAYMENT_STATUS_WAITING_ADMIN}:
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
            order_id=order_id,
        )
        mark_manual_payment_approved(order_id, callback.from_user.id)
        add_bot_log(
            "payment_approved",
            telegram_id=telegram_id,
            username=row_get(user, "username"),
            key_id=result.get("key_id"),
            order_id=order_id,
            message=f"Оплата подтверждена админом {callback.from_user.id}: тариф={tariff_code}",
        )
    except XUIError:
        reopen_manual_payment(order_id)
        logger.exception(
            "XUI error during manual payment approval: order_id=%s admin_id=%s user_id=%s",
            order_id,
            callback.from_user.id,
            telegram_id,
        )
        add_bot_log(
            "key_issue_error",
            telegram_id=telegram_id,
            username=row_get(user, "username"),
            order_id=order_id,
            message=f"Ошибка XUI при выдаче платного ключа: тариф={tariff_code}",
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
        add_bot_log(
            "key_issue_error",
            telegram_id=telegram_id,
            username=row_get(user, "username"),
            order_id=order_id,
            message=f"Ошибка обработки оплаченной заявки: тариф={tariff_code}",
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
