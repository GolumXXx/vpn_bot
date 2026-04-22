import logging
import os
from datetime import datetime

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, CopyTextButton, InlineKeyboardButton, InlineKeyboardMarkup
from dotenv import load_dotenv

from database.db import (
    delete_key_completely,
    extend_key,
    get_key_by_id,
    get_user,
    get_user_keys,
    is_key_active,
    parse_datetime,
)
from services.short_links import resolve_vless_link


load_dotenv()
router = Router()
logger = logging.getLogger(__name__)


def parse_admin_ids(raw_value: str) -> set[int]:
    admin_ids = set()
    for item in raw_value.split(","):
        item = item.strip()
        if item.isdigit():
            admin_ids.add(int(item))
    return admin_ids


ADMIN_IDS = parse_admin_ids(os.getenv("ADMIN_IDS", ""))

GENERIC_ERROR_TEXT = (
    "Что-то пошло не так 😕\n\n"
    "Попробуй ещё раз или обратись в поддержку."
)

VPN_KEY_ERROR_TEXT = (
    "Не удалось подготовить VPN-ключ.\n\n"
    "Попробуй ещё раз позже или обратись в поддержку."
)

BACK_TO_MAIN_KEYBOARD = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_main")]
    ]
)

DEVICE_TITLES = {
    "android": "🤖 Android",
    "ios": "🍎 iPhone",
    "mac": "💻 Mac",
    "windows": "🪟 Windows",
}

DEVICE_CONFIGS = {
    "android": {
        "apps": [
            ("📲 Установить Happ", "https://play.google.com/store/apps/details?id=com.happproxy&hl=ru"),
            ("📦 Скачать v2rayNG", "https://github.com/2dust/v2rayNG/releases"),
        ],
        "steps": [
            "Установи приложение",
            "Скопируй ключ",
            "Импортируй ключ в приложение",
        ],
    },
    "ios": {
        "apps": [
            ("📲 Установить v2RayTun", "https://apps.apple.com/us/app/v2raytun/id6476628951"),
            ("📲 Установить Happ", "https://apps.apple.com/us/app/happ-proxy-utility/id6504287215"),
        ],
        "steps": [
            "Установи приложение",
            "Скопируй ключ",
            "Добавь ключ в приложение",
        ],
    },
    "windows": {
        "apps": [
            ("💻 Скачать v2rayN", "https://github.com/2dust/v2rayN/releases"),
        ],
        "steps": [
            "Скачай и открой приложение",
            "Скопируй ключ",
            "Импортируй ключ в приложение",
        ],
    },
    "mac": {
        "apps": [
            ("💻 Скачать V2RayU", "https://github.com/yanue/V2rayU/releases"),
        ],
        "steps": [
            "Скачай и открой приложение",
            "Скопируй ключ",
            "Добавь ключ в приложение",
        ],
    },
}


def row_get(row, field, default=None):
    if not row:
        return default

    try:
        value = row[field]
    except (IndexError, KeyError, TypeError):
        return default

    return value if value is not None else default


def is_subscription_active(key) -> bool:
    try:
        return is_key_active(key)
    except (IndexError, KeyError, TypeError, ValueError):
        return False


def parse_callback_int(data: str | None, prefix: str) -> int | None:
    if not data or not data.startswith(prefix):
        return None

    try:
        return int(data.removeprefix(prefix))
    except ValueError:
        return None


def get_raw_vless_key(key) -> str | None:
    key_value = row_get(key, "key_value")
    if not key_value:
        return None

    try:
        resolved_key = resolve_vless_link(key_value)
    except Exception:
        logger.exception("Failed to resolve VPN key: key_id=%s", row_get(key, "id"))
        return None

    if resolved_key and resolved_key.startswith("vless://"):
        return resolved_key

    return None


def get_key_relevance_sort_value(key):
    expires_at = parse_datetime(row_get(key, "expires_at"))
    created_at = parse_datetime(row_get(key, "created_at"))
    key_id = row_get(key, "id", 0)

    return expires_at or created_at or datetime.min, key_id


def get_primary_subscription_key(keys):
    if not keys:
        return None

    active_keys = [key for key in keys if is_subscription_active(key)]
    if active_keys:
        return max(active_keys, key=get_key_relevance_sort_value)

    return max(keys, key=get_key_relevance_sort_value)


async def safe_edit_text(callback: CallbackQuery, text: str, reply_markup=None):
    try:
        await callback.message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as error:
        if "message is not modified" not in str(error).lower():
            logger.exception("Failed to edit Telegram message")
            await callback.answer(GENERIC_ERROR_TEXT, show_alert=True)
    except Exception:
        logger.exception("Unexpected error while editing Telegram message")
        await callback.answer(GENERIC_ERROR_TEXT, show_alert=True)


def format_key_status(key) -> str:
    if is_subscription_active(key):
        return "✅ активен"

    expires_at = parse_datetime(row_get(key, "expires_at"))
    if expires_at and expires_at <= datetime.now():
        return "⏰ истёк"

    return "❌ отключён"


def format_time_left(key) -> str:
    expires_at = parse_datetime(row_get(key, "expires_at"))
    if not expires_at:
        return "без срока"

    diff = expires_at - datetime.now()
    if diff.total_seconds() <= 0:
        return "время вышло"

    days = diff.days
    hours = diff.seconds // 3600
    minutes = (diff.seconds % 3600) // 60

    if days > 0:
        return f"{days} д. {hours} ч."
    if hours > 0:
        return f"{hours} ч. {minutes} мин."
    return f"{minutes} мин."


def get_subscription_keyboard(key=None):
    rows = []
    key_id = row_get(key, "id")

    if key_id:
        rows.append(
            [
                InlineKeyboardButton(
                    text="🚀 Подключить VPN",
                    callback_data=f"connect_key_{key_id}",
                )
            ]
        )
    else:
        rows.append(
            [
                InlineKeyboardButton(
                    text="🚀 Получить VPN",
                    callback_data="renew_sub",
                )
            ]
        )

    if key_id:
        rows.append([InlineKeyboardButton(text="🔄 Обновить", callback_data="my_keys_refresh")])

    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back_main")])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_key_card_keyboard(key):
    return get_subscription_keyboard(key)


def get_device_select_keyboard(key):
    key_id = row_get(key, "id", 0)

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="iPhone", callback_data=f"device_ios:{key_id}"),
                InlineKeyboardButton(text="Android", callback_data=f"device_android:{key_id}"),
            ],
            [
                InlineKeyboardButton(text="Windows", callback_data=f"device_windows:{key_id}"),
                InlineKeyboardButton(text="Mac", callback_data=f"device_mac:{key_id}"),
            ],
            [
                InlineKeyboardButton(text="⬅️ Назад", callback_data=f"view_key_{key_id}")
            ],
        ]
    )


def get_connect_app_keyboard(key, device_code):
    key_id = row_get(key, "id", 0)
    vless_key = get_raw_vless_key(key)
    device_config = DEVICE_CONFIGS.get(device_code, {})
    app_buttons = [
        [InlineKeyboardButton(text=title, url=url)]
        for title, url in device_config.get("apps", [])
    ]
    rows = [*app_buttons]

    if vless_key:
        rows.append(
            [
                InlineKeyboardButton(
                    text="📋 Скопировать ключ",
                    copy_text=CopyTextButton(text=vless_key),
                )
            ]
        )

    rows.append(
        [
            InlineKeyboardButton(
                text="⬅️ Назад",
                callback_data=f"connect_key_{key_id}"
            )
        ]
    )

    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_device_connect_text(device_code, key) -> str:
    device_title = DEVICE_TITLES.get(device_code, "📱 Устройство")
    steps = DEVICE_CONFIGS.get(device_code, {}).get("steps", [])
    instruction = "\n".join(
        f"{index}. {step}"
        for index, step in enumerate(steps, start=1)
    )

    return (
        f"{device_title}\n\n"
        f"{instruction}\n\n"
        "Готово 🚀"
    )


def format_subscription_type(key) -> str:
    return "trial" if row_get(key, "is_trial") else "paid"

def get_subscription_status_text(key: dict) -> str:
    if not key:
        return "❌ Подписка истекла"

    return "✅ Подписка активна" if is_subscription_active(key) else "❌ Подписка истекла"


def format_expiration_date(key) -> str:
    expires_at = parse_datetime(row_get(key, "expires_at"))
    if not expires_at:
        return "без срока"

    return expires_at.strftime("%d.%m.%Y %H:%M")


def format_subscription_login(key, user=None) -> str:
    panel_email = row_get(key, "panel_email")
    if panel_email:
        return panel_email

    username = row_get(user, "username")
    if username:
        return username if username.startswith("@") else f"@{username}"

    return "—"


def build_subscription_text(key, user=None) -> str:
    if not key:
        return (
            "🔐 У тебя пока нет активного VPN-ключа\n\n"
            "Нажми кнопку ниже, чтобы подключить VPN 🚀"
        )

    login = format_subscription_login(key, user)
    status_text = get_subscription_status_text(key)
    expires_text = format_expiration_date(key)

    if is_subscription_active(key):
        return (
            f"{status_text}\n\n"
            f"Логин: {login}\n"
            f"Действует до: {expires_text}\n\n"
            "Нажми кнопку ниже, чтобы подключиться"
        )

    return (
        f"{status_text}\n\n"
        f"Логин: {login}\n"
        f"Действовала до: {expires_text}\n\n"
        "Продли доступ, чтобы снова пользоваться VPN"
    )


def build_key_card_text(key, user=None) -> str:
    return build_subscription_text(key, user)


def get_owned_key(key_id: int, user_id: int):
    key = get_key_by_id(key_id)
    if not key:
        return None, "Ключ не найден. Открой список ключей ещё раз."
    if row_get(key, "telegram_id") != user_id:
        return None, "Этот ключ недоступен."
    return key, None


def validate_connectable_key(key):
    if not key:
        return "Ключ не найден. Открой список ключей ещё раз."
    if not get_raw_vless_key(key):
        return VPN_KEY_ERROR_TEXT
    if not is_subscription_active(key):
        return "Подписка истекла. Продли доступ, чтобы подключиться."
    return None


async def render_keys_list(callback: CallbackQuery, answer_text: str | None = None):
    user = get_user(callback.from_user.id)
    if not user:
        if answer_text:
            await callback.answer(answer_text)
        await safe_edit_text(
            callback,
            "Пока не вижу твой профиль.\n\n"
            "Нажми /start и попробуй ещё раз.",
            reply_markup=BACK_TO_MAIN_KEYBOARD,
        )
        if not answer_text:
            await callback.answer()
        return

    key = get_primary_subscription_key(get_user_keys(callback.from_user.id))
    await safe_edit_text(
        callback,
        build_subscription_text(key, user),
        reply_markup=get_subscription_keyboard(key),
    )
    if answer_text:
        await callback.answer(answer_text)
    else:
        await callback.answer()


async def render_key_card(callback: CallbackQuery, key, answer_text: str | None = None):
    user = get_user(callback.from_user.id)
    await safe_edit_text(
        callback,
        build_key_card_text(key, user),
        reply_markup=get_key_card_keyboard(key),
    )
    if answer_text:
        await callback.answer(answer_text)
    else:
        await callback.answer()


@router.callback_query(F.data == "my_keys")
async def my_keys_handler(callback: CallbackQuery):
    await render_keys_list(callback)


@router.callback_query(F.data == "my_keys_refresh")
async def my_keys_refresh_handler(callback: CallbackQuery):
    await render_keys_list(callback, "Готово")


@router.callback_query(F.data.startswith("view_key_"))
async def view_key_handler(callback: CallbackQuery):
    key_id = parse_callback_int(callback.data, "view_key_")
    if key_id is None:
        logger.warning("Invalid view_key callback data: data=%s user_id=%s", callback.data, callback.from_user.id)
        await callback.answer(GENERIC_ERROR_TEXT, show_alert=True)
        return

    key, error = get_owned_key(key_id, callback.from_user.id)
    if error:
        await callback.answer(error, show_alert=True)
        return

    await render_key_card(callback, key)


@router.callback_query(F.data.startswith("refresh_key_"))
async def refresh_key_handler(callback: CallbackQuery):
    key_id = parse_callback_int(callback.data, "refresh_key_")
    if key_id is None:
        logger.warning("Invalid refresh_key callback data: data=%s user_id=%s", callback.data, callback.from_user.id)
        await callback.answer(GENERIC_ERROR_TEXT, show_alert=True)
        return

    key, error = get_owned_key(key_id, callback.from_user.id)
    if error:
        await callback.answer(error, show_alert=True)
        return

    await render_key_card(callback, key, "Готово")


@router.callback_query(F.data.startswith("extend_key:"))
async def extend_key_handler(callback: CallbackQuery):
    try:
        _, key_id_str, days_str = callback.data.split(":")
        key_id = int(key_id_str)
        days = int(days_str)
    except (AttributeError, ValueError):
        logger.warning("Invalid extend_key callback data: data=%s user_id=%s", callback.data, callback.from_user.id)
        await callback.answer(GENERIC_ERROR_TEXT, show_alert=True)
        return

    key, error = get_owned_key(key_id, callback.from_user.id)
    if error:
        await callback.answer(error, show_alert=True)
        return

    if row_get(key, "is_trial"):
        await callback.answer("Пробный доступ нельзя продлить", show_alert=True)
        return

    try:
        extend_key(key_id, days)
    except Exception:
        logger.exception(
            "Failed to extend VPN key: user_id=%s key_id=%s days=%s",
            callback.from_user.id,
            key_id,
            days,
        )
        await callback.answer(GENERIC_ERROR_TEXT, show_alert=True)
        return

    logger.info(
        "Extended VPN key: user_id=%s key_id=%s days=%s",
        callback.from_user.id,
        key_id,
        days,
    )
    updated_key = get_key_by_id(key_id)
    await render_key_card(callback, updated_key, f"Подписка продлена на {days} дней")


@router.callback_query(F.data.startswith("delete_key_confirm:"))
async def delete_key_handler(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("Нет доступа", show_alert=True)
        return

    try:
        key_id = int(callback.data.split(":")[1])
    except (AttributeError, IndexError, ValueError):
        logger.warning("Invalid delete_key_confirm callback data: data=%s user_id=%s", callback.data, callback.from_user.id)
        await callback.answer(GENERIC_ERROR_TEXT, show_alert=True)
        return

    try:
        success, message = await delete_key_completely(key_id)
    except Exception:
        logger.exception(
            "Failed to delete VPN key: user_id=%s key_id=%s",
            callback.from_user.id,
            key_id,
        )
        await callback.answer(GENERIC_ERROR_TEXT, show_alert=True)
        return

    if not success:
        logger.warning(
            "VPN key deletion rejected: user_id=%s key_id=%s message=%s",
            callback.from_user.id,
            key_id,
            message,
        )
        await callback.answer(GENERIC_ERROR_TEXT, show_alert=True)
        return

    logger.info("Deleted VPN key: user_id=%s key_id=%s", callback.from_user.id, key_id)
    await render_keys_list(callback, "Ключ удалён ✅")


@router.callback_query(F.data.startswith("delete_key:"))
async def confirm_delete_key_handler(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("Нет доступа", show_alert=True)
        return

    try:
        key_id = int(callback.data.split(":")[1])
    except (AttributeError, IndexError, ValueError):
        logger.warning("Invalid delete_key callback data: data=%s user_id=%s", callback.data, callback.from_user.id)
        await callback.answer(GENERIC_ERROR_TEXT, show_alert=True)
        return

    key = get_key_by_id(key_id)
    if not key:
        await callback.answer("Ключ не найден. Открой список ключей ещё раз.", show_alert=True)
        return

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Да, удалить",
                    callback_data=f"delete_key_confirm:{key_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отмена",
                    callback_data=f"view_key_{key_id}",
                )
            ],
        ]
    )

    await safe_edit_text(
        callback,
        "Удалить этот ключ?\n\n"
        f"🔑 {row_get(key, 'key_name', 'VPN-ключ')}\n"
        f"ID: {key_id}",
        reply_markup=kb,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("connect_key_"))
async def connect_key_handler(callback: CallbackQuery):
    key_id = parse_callback_int(callback.data, "connect_key_")
    if key_id is None:
        logger.warning("Invalid connect_key callback data: data=%s user_id=%s", callback.data, callback.from_user.id)
        await callback.answer(GENERIC_ERROR_TEXT, show_alert=True)
        return

    key, error = get_owned_key(key_id, callback.from_user.id)
    if error:
        await callback.answer(error, show_alert=True)
        return

    connect_error = validate_connectable_key(key)
    if connect_error:
        await callback.answer(connect_error, show_alert=True)
        return

    await safe_edit_text(
        callback,
        "📱 Подключение VPN\n\n"
        "Выбери устройство:",
        reply_markup=get_device_select_keyboard(key),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("device_"))
async def device_handler(callback: CallbackQuery):
    try:
        device_part, key_id_str = callback.data.split(":", maxsplit=1)
        key_id = int(key_id_str)
    except (ValueError, AttributeError):
        logger.warning("Invalid device callback data: data=%s user_id=%s", callback.data, callback.from_user.id)
        await callback.answer("Не удалось открыть подключение. Попробуй ещё раз.", show_alert=True)
        return

    device_code = device_part.removeprefix("device_")

    device_title = DEVICE_TITLES.get(device_code)
    if not device_title:
        await callback.answer("Это устройство пока не поддерживается", show_alert=True)
        return

    key, error = get_owned_key(key_id, callback.from_user.id)
    if error:
        await callback.answer(error, show_alert=True)
        return

    connect_error = validate_connectable_key(key)
    if connect_error:
        await callback.answer(connect_error, show_alert=True)
        return

    await safe_edit_text(
        callback,
        build_device_connect_text(device_code, key),
        reply_markup=get_connect_app_keyboard(key, device_code),
    )
    await callback.answer()
