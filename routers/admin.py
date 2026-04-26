import asyncio
import logging
from datetime import datetime

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from config import ADMIN_IDS
from database.db import (
    MANUAL_PAYMENT_STATUS_PENDING,
    add_bot_log,
    cancel_pending_manual_payment,
    clear_bot_logs,
    delete_key_completely,
    extend_key_with_panel,
    get_admin_dashboard_stats,
    get_connection,
    get_key_by_id,
    get_latest_bot_logs,
    get_manual_payment_by_order_id,
    get_pending_manual_payments,
    get_user,
    get_user_by_username,
    get_user_keys,
    get_user_key_stats,
    is_key_active,
    mark_manual_payment_reminded,
    parse_datetime,
)
from keyboards import (
    admin_back_menu,
    admin_broadcast_confirm_menu,
    admin_logs_clear_confirm_menu,
    admin_logs_menu,
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


class BroadcastState(StatesGroup):
    waiting_text = State()


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


def get_broadcast_user_ids() -> list[int]:
    with get_connection() as conn:
        rows = conn.execute("SELECT telegram_id FROM users").fetchall()

    return [row["telegram_id"] for row in rows]


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


def format_payment_status(payment) -> str:
    status = row_get(payment, "status", "—")
    if status == "pending_receipt":
        return "⏳ Ожидаем чек"

    return status


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
                f"Статус: {format_payment_status(payment)}",
                "",
            ]
        )

    return "\n".join(lines).rstrip()


def format_log_message(log) -> str:
    message = row_get(log, "message")
    if not message:
        return "—"

    message = str(message).replace("\n", " ").strip()
    if len(message) > 80:
        return f"{message[:79]}…"
    return message


def build_admin_logs_text(logs) -> str:
    if not logs:
        return "📜 Логи\n\nСобытий пока нет."

    lines = ["📜 Логи", "", "Последние 20 событий:"]
    for log in logs:
        meta = []
        telegram_id = row_get(log, "telegram_id")
        key_id = row_get(log, "key_id")
        order_id = row_get(log, "order_id")

        if telegram_id:
            meta.append(f"user_id={telegram_id}")
        if key_id:
            meta.append(f"key_id={key_id}")
        if order_id:
            meta.append(f"order_id={order_id}")

        lines.extend(
            [
                "",
                f"{row_get(log, 'created_at', '—')}",
                f"Тип: {row_get(log, 'event_type', '—')}",
                " ".join(meta) if meta else "Без привязки",
                f"Сообщение: {format_log_message(log)}",
            ]
        )

    return "\n".join(lines)


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
        "Отправь telegram_id пользователя, чтобы посмотреть его ключи."
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
        panel_email = row_get(key, "panel_email")
        if panel_email:
            lines.append(f"Panel email: {panel_email}")

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
async def admin_command_handler(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Доступ запрещён")
        return

    await state.clear()
    clear_admin_waiting_state(message.from_user.id)
    await show_admin_menu(message)


@router.callback_query(F.data == "admin_menu")
@router.callback_query(F.data == "admin_panel")
async def admin_menu_handler(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return

    await state.clear()
    clear_admin_waiting_state(callback.from_user.id)
    await show_admin_menu(callback)


@router.callback_query(F.data == "admin_broadcast")
async def admin_broadcast_handler(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return

    clear_admin_waiting_state(callback.from_user.id)
    await state.set_state(BroadcastState.waiting_text)
    await safe_edit_text(
        callback.message,
        "✍️ Отправь текст для рассылки",
        reply_markup=admin_back_menu,
    )
    await callback.answer()


@router.message(BroadcastState.waiting_text)
async def admin_broadcast_text_handler(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.clear()
        return

    text = (message.text or "").strip()
    if not text:
        await message.answer(
            "Отправь текст для рассылки.",
            reply_markup=admin_back_menu,
        )
        return

    await state.update_data(broadcast_text=text)
    await message.answer(
        "Отправить сообщение всем пользователям?",
        reply_markup=admin_broadcast_confirm_menu,
    )


@router.callback_query(F.data == "admin_broadcast_confirm")
async def admin_broadcast_confirm_handler(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return

    data = await state.get_data()
    text = data.get("broadcast_text")
    if not text:
        await state.clear()
        await safe_edit_text(
            callback.message,
            "Текст рассылки не найден. Начни заново.",
            reply_markup=admin_back_menu,
        )
        await callback.answer("Нет текста для рассылки", show_alert=True)
        return

    await callback.answer("Рассылка началась")
    await safe_edit_text(callback.message, "⏳ Отправляю рассылку...")

    users = get_broadcast_user_ids()
    for user_id in users:
        try:
            await callback.bot.send_message(user_id, text)
        except Exception:
            pass
        await asyncio.sleep(0.05)

    add_bot_log(
        "admin_broadcast",
        telegram_id=callback.from_user.id,
        username=callback.from_user.username,
        message=f"Рассылка отправлена пользователям: {len(users)}",
    )
    await state.clear()
    await safe_edit_text(
        callback.message,
        "✅ Рассылка завершена",
        reply_markup=admin_back_menu,
    )


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

    await render_admin_payments(callback)


async def render_admin_payments(callback: CallbackQuery, answer_text: str | None = None):
    payments = get_pending_manual_payments()
    await safe_edit_text(
        callback.message,
        build_pending_payments_text(payments),
        reply_markup=get_admin_pending_payments_menu(payments),
    )
    if answer_text:
        await callback.answer(answer_text, show_alert=True)
    else:
        await callback.answer()


async def render_admin_logs(callback: CallbackQuery, answer_text: str | None = None):
    await safe_edit_text(
        callback.message,
        build_admin_logs_text(get_latest_bot_logs(20)),
        reply_markup=admin_logs_menu,
    )
    if answer_text:
        await callback.answer(answer_text)
    else:
        await callback.answer()


@router.callback_query(F.data == "admin_logs")
async def admin_logs_handler(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return

    clear_admin_waiting_state(callback.from_user.id)
    await render_admin_logs(callback)


@router.callback_query(F.data == "admin_logs_clear")
async def admin_logs_clear_handler(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return

    clear_admin_waiting_state(callback.from_user.id)
    await safe_edit_text(
        callback.message,
        "⚠️ Ты точно хочешь удалить ВСЕ логи?\n\n"
        "Это действие нельзя отменить.",
        reply_markup=admin_logs_clear_confirm_menu,
    )
    await callback.answer()


@router.callback_query(F.data == "admin_logs_clear_confirm")
async def admin_logs_clear_confirm_handler(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return

    clear_bot_logs()
    await render_admin_logs(callback, "🗑 Логи успешно очищены")


@router.callback_query(F.data.startswith("admin_remind_payment:"))
async def admin_remind_payment_handler(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return

    try:
        order_id = callback.data.split(":", maxsplit=1)[1].strip()
    except (AttributeError, IndexError):
        logger.warning("Invalid admin remind payment callback: data=%s user_id=%s", callback.data, callback.from_user.id)
        await callback.answer("Не удалось отправить напоминание", show_alert=True)
        return

    payment = get_manual_payment_by_order_id(order_id)
    if not payment:
        await callback.answer("Заявка не найдена", show_alert=True)
        return

    if row_get(payment, "status") != MANUAL_PAYMENT_STATUS_PENDING:
        await callback.answer("Заявка уже не ждёт чек", show_alert=True)
        return

    if not mark_manual_payment_reminded(order_id):
        await callback.answer("Напоминание уже отправлялось", show_alert=True)
        return

    try:
        await callback.bot.send_message(
            chat_id=row_get(payment, "telegram_id"),
            text=(
                f"⏳ Мы ждём чек по заявке {order_id}. "
                "Если оплатил — отправь фото чека в этот чат."
            ),
        )
    except Exception:
        logger.exception(
            "Failed to send manual payment reminder: order_id=%s admin_id=%s user_id=%s",
            order_id,
            callback.from_user.id,
            row_get(payment, "telegram_id"),
        )
        await callback.answer("Не удалось отправить напоминание", show_alert=True)
        return

    await callback.answer("Напоминание отправлено", show_alert=True)


@router.callback_query(F.data.startswith("admin_cancel_payment:"))
async def admin_cancel_payment_handler(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return

    try:
        order_id = callback.data.split(":", maxsplit=1)[1].strip()
    except (AttributeError, IndexError):
        logger.warning("Invalid admin cancel payment callback: data=%s user_id=%s", callback.data, callback.from_user.id)
        await callback.answer("Не удалось отменить заявку", show_alert=True)
        return

    payment = get_manual_payment_by_order_id(order_id)
    if not payment:
        await callback.answer("Заявка не найдена", show_alert=True)
        return

    if row_get(payment, "status") != MANUAL_PAYMENT_STATUS_PENDING:
        await callback.answer("Заявка уже не ждёт чек", show_alert=True)
        return

    if not cancel_pending_manual_payment(order_id):
        await callback.answer("Не удалось отменить заявку", show_alert=True)
        return

    user = get_user(row_get(payment, "telegram_id"))
    add_bot_log(
        "payment_cancelled_admin",
        telegram_id=row_get(payment, "telegram_id"),
        username=row_get(user, "username"),
        order_id=order_id,
        message=f"Заявка отменена админом {callback.from_user.id}",
    )

    try:
        await callback.bot.send_message(
            chat_id=row_get(payment, "telegram_id"),
            text="❌ Заявка отменена. Если нужна помощь — напиши в поддержку.",
        )
    except Exception:
        logger.exception(
            "Failed to notify user about cancelled manual payment: order_id=%s admin_id=%s user_id=%s",
            order_id,
            callback.from_user.id,
            row_get(payment, "telegram_id"),
        )

    await render_admin_payments(callback, "Заявка отменена")


async def render_admin_user_keys(callback: CallbackQuery, telegram_id: int):
    user = get_user(telegram_id)
    if not user:
        await callback.answer("Пользователь не найден", show_alert=True)
        return

    keys = get_user_keys(telegram_id)
    await safe_edit_text(
        callback.message,
        build_admin_user_keys_text(user, keys),
        reply_markup=get_admin_user_keys_menu(keys),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_user_keys:"))
async def admin_user_keys_handler(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return

    try:
        telegram_id = int(callback.data.split(":", maxsplit=1)[1])
    except (AttributeError, IndexError, ValueError):
        logger.warning("Invalid admin user keys callback data: data=%s user_id=%s", callback.data, callback.from_user.id)
        await callback.answer("Не удалось открыть пользователя", show_alert=True)
        return

    clear_admin_waiting_state(callback.from_user.id)
    await render_admin_user_keys(callback, telegram_id)


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
                "Отправь telegram_id пользователя, чтобы посмотреть его ключи.",
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
        new_expires = await extend_key_with_panel(key_id, 30)
    except Exception:
        logger.exception("Failed to extend key from admin panel: admin_id=%s key_id=%s", callback.from_user.id, key_id)
        await callback.answer("Не удалось продлить ключ", show_alert=True)
        return

    telegram_id = row_get(key, "telegram_id")
    user = get_user(telegram_id)
    add_bot_log(
        "key_extended_admin",
        telegram_id=telegram_id,
        username=row_get(user, "username"),
        key_id=key_id,
        message=f"Ключ продлён админом {callback.from_user.id} до {new_expires}",
    )
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
        "Вы точно хотите удалить этот ключ?\n\n"
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
    add_bot_log(
        "key_deleted_admin",
        telegram_id=telegram_id,
        username=row_get(user, "username"),
        key_id=key_id,
        message=message or f"Ключ удалён админом {callback.from_user.id}",
    )
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
async def admin_close_handler(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        return

    await state.clear()
    clear_admin_waiting_state(callback.from_user.id)
    try:
        await callback.message.delete()
    except Exception:
        logger.exception("Failed to delete admin panel message")
        await safe_edit_text(callback.message, "Админ-панель закрыта.")

    await callback.answer()
