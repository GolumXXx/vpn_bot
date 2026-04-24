import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from config import ADMIN_IDS
from database.db import (
    get_admin_dashboard_stats,
    get_pending_manual_payments,
    get_user,
    get_user_by_username,
    get_user_key_stats,
)
from keyboards import (
    admin_back_menu,
    admin_menu,
    get_admin_pending_payments_menu,
)
from routers.payments import TARIFFS
from routers.ui import safe_edit_text


router = Router()
logger = logging.getLogger(__name__)
ADMIN_ID_SET = set(ADMIN_IDS)
WAITING_SEARCH_ADMINS = set()

ADMIN_MENU_TEXT = (
    "🛠 Админ-панель\n\n"
    "Выбери раздел:"
)


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_ID_SET


def row_get(row, field, default=None):
    if not row:
        return default

    try:
        value = row[field]
    except (IndexError, KeyError, TypeError):
        return default

    return value if value is not None else default


def build_dashboard_text() -> str:
    stats = get_admin_dashboard_stats()
    return (
        "📊 Дашборд\n\n"
        f"Пользователей: {stats['users']}\n"
        f"Ключей всего: {stats['total_keys']}\n"
        f"Активных ключей: {stats['active_keys']}\n"
        f"Истёкших ключей: {stats['expired_keys']}\n"
        f"Ожидающих оплат: {stats['pending_payments']}"
    )


def format_tariff(payment) -> str:
    tariff_code = row_get(payment, "tariff_code", "—")
    tariff = TARIFFS.get(tariff_code)
    if not tariff:
        return str(tariff_code)

    return f"{tariff['label']} ({tariff_code})"


def format_price(payment) -> str:
    tariff = TARIFFS.get(row_get(payment, "tariff_code"))
    if not tariff:
        return "—"

    return f"{tariff['price']} ₽"


def build_pending_payments_text(payments) -> str:
    if not payments:
        return "💰 Ожидающие оплаты\n\nНет ожидающих оплат ✅"

    lines = ["💰 Ожидающие оплаты", ""]
    for payment in payments:
        lines.extend(
            [
                f"ID: {row_get(payment, 'order_id', '—')}",
                f"Пользователь: {row_get(payment, 'telegram_id', '—')}",
                f"Тариф: {format_tariff(payment)}",
                f"Стоимость: {format_price(payment)}",
                f"Статус: {row_get(payment, 'status', '—')}",
                "",
            ]
        )

    return "\n".join(lines).rstrip()


def build_user_search_text(user) -> str:
    key_stats = get_user_key_stats(user["telegram_id"])
    username = f"@{user['username']}" if user["username"] else "нет"

    return (
        "🔍 Пользователь\n\n"
        f"ID: {user['telegram_id']}\n"
        f"Имя: {user['first_name'] or '—'}\n"
        f"Username: {username}\n"
        f"Пробный период использован: {'да' if user['used_trial'] else 'нет'}\n\n"
        "🔑 Ключи:\n"
        f"Всего: {key_stats['total_keys']}\n"
        f"Активных: {key_stats['active_keys']}"
    )


async def show_admin_menu(message_or_callback):
    message = getattr(message_or_callback, "message", message_or_callback)
    if isinstance(message_or_callback, CallbackQuery):
        await safe_edit_text(message, ADMIN_MENU_TEXT, reply_markup=admin_menu)
        await message_or_callback.answer()
        return

    await message.answer(ADMIN_MENU_TEXT, reply_markup=admin_menu)


@router.message(Command("admin"))
async def admin_command_handler(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Доступ запрещён")
        return

    await show_admin_menu(message)


@router.callback_query(F.data == "admin_menu")
async def admin_menu_handler(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return

    await show_admin_menu(callback)


@router.callback_query(F.data == "admin_dashboard")
async def admin_dashboard_handler(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return

    await safe_edit_text(
        callback.message,
        build_dashboard_text(),
        reply_markup=admin_back_menu,
    )
    await callback.answer()


@router.callback_query(F.data == "admin_payments")
async def admin_payments_handler(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return

    payments = get_pending_manual_payments()
    await safe_edit_text(
        callback.message,
        build_pending_payments_text(payments),
        reply_markup=get_admin_pending_payments_menu(payments),
    )
    await callback.answer()


@router.callback_query(F.data == "admin_search")
async def admin_search_handler(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return

    WAITING_SEARCH_ADMINS.add(callback.from_user.id)
    await safe_edit_text(
        callback.message,
        "🔍 Поиск пользователей\n\n"
        "Отправь telegram_id или @username.",
        reply_markup=admin_back_menu,
    )
    await callback.answer()


@router.message(F.text)
async def admin_search_message_handler(message: Message):
    if not is_admin(message.from_user.id) or message.from_user.id not in WAITING_SEARCH_ADMINS:
        return

    query = message.text.strip()
    if query.isdigit():
        user = get_user(int(query))
    elif query.startswith("@"):
        user = get_user_by_username(query)
    else:
        await message.answer(
            "Отправь telegram_id или @username.",
            reply_markup=admin_back_menu,
        )
        return

    WAITING_SEARCH_ADMINS.discard(message.from_user.id)

    if not user:
        await message.answer(
            "Пользователь не найден.",
            reply_markup=admin_back_menu,
        )
        return

    await message.answer(
        build_user_search_text(user),
        reply_markup=admin_back_menu,
    )


@router.callback_query(F.data == "admin_settings")
async def admin_settings_handler(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return

    await safe_edit_text(
        callback.message,
        "⚙️ Настройки\n\n"
        "Настройки будут добавлены позже.",
        reply_markup=admin_back_menu,
    )
    await callback.answer()


@router.callback_query(F.data == "admin_close")
async def admin_close_handler(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return

    WAITING_SEARCH_ADMINS.discard(callback.from_user.id)
    try:
        await callback.message.delete()
    except Exception:
        logger.exception("Failed to delete admin panel message")
        await safe_edit_text(callback.message, "Админ-панель закрыта.")

    await callback.answer()
