import logging
from datetime import datetime

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from config import ADMIN_IDS
from database.db import (
    delete_key_completely,
    extend_key,
    get_admin_dashboard_stats,
    get_key_by_id,
    get_pending_manual_payments,
    get_user,
    get_user_by_username,
    get_user_keys,
    get_user_key_stats,
    is_key_active,
    parse_datetime,
)
from keyboards import (
    admin_back_menu,
    admin_menu,
    get_admin_delete_key_confirm_menu,
    get_admin_pending_payments_menu,
    get_admin_user_keys_menu,
)
from routers.payments import TARIFFS
from routers.ui import safe_edit_text


router = Router()
logger = logging.getLogger(__name__)
ADMIN_ID_SET = set(ADMIN_IDS)
WAITING_SEARCH_ADMINS = set()
WAITING_KEY_SEARCH_ADMINS = set()

ADMIN_MENU_TEXT = (
    "🛠 Админ-панель\n\n"
    "Выбери раздел:"
)


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_ID_SET


def clear_admin_waiting_state(user_id: int):
    WAITING_SEARCH_ADMINS.discard(user_id)
    WAITING_KEY_SEARCH_ADMINS.discard(user_id)


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


def format_key_status(key) -> str:
    try:
        if is_key_active(key):
            return "активен"
    except (IndexError, KeyError, TypeError, ValueError):
        pass

    expires_at = parse_datetime(row_get(key, "expires_at"))
    if expires_at and expires_at <= datetime.now():
        return "истёк"

    return "неактивен"


def build_admin_keys_text() -> str:
    return (
        "🔑 Управление ключами\n\n"
        "Отправь telegram_id пользователя."
    )


def build_admin_user_keys_text(user, keys) -> str:
    username = f"@{user['username']}" if row_get(user, "username") else "нет"
    lines = [
        "🔑 Управление ключами",
        "",
        f"Пользователь: {row_get(user, 'telegram_id', '—')}",
        f"Username: {username}",
        f"Имя: {row_get(user, 'first_name', '—')}",
        "",
    ]

    if not keys:
        lines.append("Ключей нет.")
        return "\n".join(lines)

    lines.append("Ключи:")
    for key in keys:
        lines.extend(
            [
                "",
                f"ID: {row_get(key, 'id', '—')}",
                f"Название: {row_get(key, 'key_name', 'VPN-ключ')}",
                f"Статус: {format_key_status(key)}",
                f"Действует до: {row_get(key, 'expires_at', '—')}",
            ]
        )

    return "\n".join(lines)


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

    clear_admin_waiting_state(message.from_user.id)
    await show_admin_menu(message)


@router.callback_query(F.data == "admin_menu")
async def admin_menu_handler(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return

    clear_admin_waiting_state(callback.from_user.id)
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


@router.callback_query(F.data == "admin_keys")
async def admin_keys_handler(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return

    WAITING_SEARCH_ADMINS.discard(callback.from_user.id)
    WAITING_KEY_SEARCH_ADMINS.add(callback.from_user.id)
    await safe_edit_text(
        callback.message,
        build_admin_keys_text(),
        reply_markup=admin_back_menu,
    )
    await callback.answer()


@router.callback_query(F.data == "admin_search")
async def admin_search_handler(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return

    WAITING_KEY_SEARCH_ADMINS.discard(callback.from_user.id)
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
    if not is_admin(message.from_user.id):
        return

    if message.from_user.id in WAITING_KEY_SEARCH_ADMINS:
        query = message.text.strip()
        if not query.isdigit():
            await message.answer(
                "Отправь telegram_id пользователя.",
                reply_markup=admin_back_menu,
            )
            return

        WAITING_KEY_SEARCH_ADMINS.discard(message.from_user.id)
        telegram_id = int(query)
        user = get_user(telegram_id)
        if not user:
            await message.answer(
                "Пользователь не найден.",
                reply_markup=admin_back_menu,
            )
            return

        keys = get_user_keys(telegram_id)
        await message.answer(
            build_admin_user_keys_text(user, keys),
            reply_markup=get_admin_user_keys_menu(keys),
        )
        return

    if message.from_user.id not in WAITING_SEARCH_ADMINS:
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


@router.callback_query(F.data.startswith("admin_key:"))
async def admin_key_handler(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return

    try:
        key_id = int(callback.data.split(":", maxsplit=1)[1])
    except (AttributeError, IndexError, ValueError):
        logger.warning("Invalid admin key callback data: data=%s user_id=%s", callback.data, callback.from_user.id)
        await callback.answer("Не удалось открыть ключ", show_alert=True)
        return

    key = get_key_by_id(key_id)
    if not key:
        await callback.answer("Ключ не найден", show_alert=True)
        return

    telegram_id = row_get(key, "telegram_id")
    user = get_user(telegram_id)
    keys = get_user_keys(telegram_id)
    await safe_edit_text(
        callback.message,
        build_admin_user_keys_text(user, keys),
        reply_markup=get_admin_user_keys_menu(keys),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_extend_key:"))
async def admin_extend_key_handler(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return

    try:
        key_id = int(callback.data.split(":", maxsplit=1)[1])
    except (AttributeError, IndexError, ValueError):
        logger.warning("Invalid admin extend key callback data: data=%s user_id=%s", callback.data, callback.from_user.id)
        await callback.answer("Не удалось продлить ключ", show_alert=True)
        return

    key = get_key_by_id(key_id)
    if not key:
        await callback.answer("Ключ не найден", show_alert=True)
        return

    try:
        extend_key(key_id, 30)
    except Exception:
        logger.exception("Failed to extend key from admin panel: admin_id=%s key_id=%s", callback.from_user.id, key_id)
        await callback.answer("Не удалось продлить ключ", show_alert=True)
        return

    telegram_id = row_get(key, "telegram_id")
    user = get_user(telegram_id)
    keys = get_user_keys(telegram_id)
    await safe_edit_text(
        callback.message,
        build_admin_user_keys_text(user, keys),
        reply_markup=get_admin_user_keys_menu(keys),
    )
    await callback.answer("Ключ продлён на 30 дней ✅", show_alert=True)


@router.callback_query(F.data.startswith("admin_delete_key:"))
async def admin_delete_key_handler(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return

    try:
        key_id = int(callback.data.split(":", maxsplit=1)[1])
    except (AttributeError, IndexError, ValueError):
        logger.warning("Invalid admin delete key callback data: data=%s user_id=%s", callback.data, callback.from_user.id)
        await callback.answer("Не удалось удалить ключ", show_alert=True)
        return

    key = get_key_by_id(key_id)
    if not key:
        await callback.answer("Ключ не найден", show_alert=True)
        return

    await safe_edit_text(
        callback.message,
        "Удалить этот ключ?\n\n"
        f"ID: {row_get(key, 'id', '—')}\n"
        f"Пользователь: {row_get(key, 'telegram_id', '—')}\n"
        f"Название: {row_get(key, 'key_name', 'VPN-ключ')}\n"
        f"Действует до: {row_get(key, 'expires_at', '—')}",
        reply_markup=get_admin_delete_key_confirm_menu(key_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_delete_key_confirm:"))
async def admin_delete_key_confirm_handler(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return

    try:
        key_id = int(callback.data.split(":", maxsplit=1)[1])
    except (AttributeError, IndexError, ValueError):
        logger.warning("Invalid admin delete key confirm callback data: data=%s user_id=%s", callback.data, callback.from_user.id)
        await callback.answer("Не удалось удалить ключ", show_alert=True)
        return

    key = get_key_by_id(key_id)
    if not key:
        await callback.answer("Ключ не найден", show_alert=True)
        return

    telegram_id = row_get(key, "telegram_id")
    try:
        success, message = await delete_key_completely(key_id)
    except Exception:
        logger.exception("Failed to delete key from admin panel: admin_id=%s key_id=%s", callback.from_user.id, key_id)
        await callback.answer("Не удалось удалить ключ", show_alert=True)
        return

    if not success:
        logger.warning(
            "Admin key deletion rejected: admin_id=%s key_id=%s message=%s",
            callback.from_user.id,
            key_id,
            message,
        )
        await callback.answer(message or "Не удалось удалить ключ", show_alert=True)
        return

    user = get_user(telegram_id)
    keys = get_user_keys(telegram_id)
    await safe_edit_text(
        callback.message,
        build_admin_user_keys_text(user, keys),
        reply_markup=get_admin_user_keys_menu(keys),
    )
    await callback.answer("Ключ удалён ✅", show_alert=True)


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

    clear_admin_waiting_state(callback.from_user.id)
    try:
        await callback.message.delete()
    except Exception:
        logger.exception("Failed to delete admin panel message")
        await safe_edit_text(callback.message, "Админ-панель закрыта.")

    await callback.answer()
