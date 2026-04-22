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


def parse_admin_ids(raw_value: str) -> set[int]:
    admin_ids = set()
    for item in raw_value.split(","):
        item = item.strip()
        if item.isdigit():
            admin_ids.add(int(item))
    return admin_ids


ADMIN_IDS = parse_admin_ids(os.getenv("ADMIN_IDS", ""))

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
            "Установи Happ или v2rayNG",
            "Открой приложение",
            "Скопируй ключ кнопкой ниже",
            'Нажми "+" -> Import from clipboard',
        ],
    },
    "ios": {
        "apps": [
            ("📲 Установить v2RayTun", "https://apps.apple.com/us/app/v2raytun/id6476628951"),
            ("📲 Установить Happ", "https://apps.apple.com/us/app/happ-proxy-utility/id6504287215"),
        ],
        "steps": [
            "Установи v2RayTun или Happ",
            "Открой приложение",
            "Скопируй ключ кнопкой ниже",
            'Нажми "Add config"',
        ],
    },
    "windows": {
        "apps": [
            ("💻 Скачать v2rayN", "https://github.com/2dust/v2rayN/releases"),
        ],
        "steps": [
            "Скачай v2rayN",
            "Распакуй архив",
            "Запусти v2rayN.exe",
            "Скопируй ключ кнопкой ниже",
            'Нажми "Import from clipboard"',
        ],
    },
    "mac": {
        "apps": [
            ("💻 Скачать V2RayU", "https://github.com/yanue/V2rayU/releases"),
        ],
        "steps": [
            "Скачай V2RayU",
            "Открой клиент",
            "Скопируй ключ кнопкой ниже",
            "Добавь конфигурацию",
        ],
    },
}


def get_raw_vless_key(key) -> str | None:
    if not key or not key["key_value"]:
        return None

    resolved_key = resolve_vless_link(key["key_value"])
    if resolved_key and resolved_key.startswith("vless://"):
        return resolved_key

    return None


def get_key_relevance_sort_value(key):
    expires_at = parse_datetime(key["expires_at"])
    created_at = parse_datetime(key["created_at"])
    key_id = key["id"] or 0

    return expires_at or created_at or datetime.min, key_id


def get_primary_subscription_key(keys):
    if not keys:
        return None

    active_keys = [key for key in keys if is_key_active(key)]
    if active_keys:
        return max(active_keys, key=get_key_relevance_sort_value)

    return max(keys, key=get_key_relevance_sort_value)


async def safe_edit_text(callback: CallbackQuery, text: str, reply_markup=None):
    try:
        await callback.message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as error:
        if "message is not modified" not in str(error).lower():
            raise


def format_key_status(key) -> str:
    if is_key_active(key):
        return "✅ активен"

    expires_at = parse_datetime(key["expires_at"])
    if expires_at and expires_at <= datetime.now():
        return "⏰ истёк"

    return "❌ отключён"


def format_time_left(key) -> str:
    expires_at = parse_datetime(key["expires_at"])
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

    if key:
        rows.append(
            [
                InlineKeyboardButton(
                    text="🚀 Подключить VPN",
                    callback_data=f"connect_key_{key['id']}",
                )
            ]
        )

    rows.extend(
        [
            [InlineKeyboardButton(text="🔄 Обновить", callback_data="my_keys_refresh")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_main")],
        ]
    )

    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_key_card_keyboard(key):
    return get_subscription_keyboard(key)


def get_device_select_keyboard(key):
    key_id = key["id"]

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
    key_id = key["id"]
    vless_key = get_raw_vless_key(key)
    device_config = DEVICE_CONFIGS[device_code]
    app_buttons = [
        [InlineKeyboardButton(text=title, url=url)]
        for title, url in device_config["apps"]
    ]

    return InlineKeyboardMarkup(
        inline_keyboard=[
            *app_buttons,
            [
                InlineKeyboardButton(
                    text="📋 Скопировать ключ",
                    copy_text=CopyTextButton(text=vless_key),
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Назад",
                    callback_data=f"connect_key_{key_id}"
                )
            ],
        ]
    )


def build_device_connect_text(device_code, key) -> str:
    device_title = DEVICE_TITLES[device_code]
    steps = DEVICE_CONFIGS[device_code]["steps"]
    instruction = "\n".join(
        f"{index}. {step}"
        for index, step in enumerate(steps, start=1)
    )

    return (
        f"{device_title}\n\n"
        f"{instruction}"
    )


def format_subscription_type(key) -> str:
    return "trial" if key["is_trial"] else "paid"

def get_subscription_status_text(key: dict) -> str:
    if not key:
        return "ЗАКОНЧИЛАСЬ ❌"

    return "АКТИВНА ✅" if is_key_active(key) else "ЗАКОНЧИЛАСЬ ❌"


def format_subscription_login(key, user=None) -> str:
    if key and key["panel_email"]:
        return key["panel_email"]

    if user and user["username"]:
        username = user["username"]
        return username if username.startswith("@") else f"@{username}"

    return "—"


def build_subscription_text(key, user=None) -> str:
    if not key:
        return (
            "🔑 Мои активные ключи\n\n"
            "У тебя пока нет ключа."
        )

    login = format_subscription_login(key, user)
    status_text = get_subscription_status_text(key)

    lines = [
        "🔑 Мои активные ключи",
        "",
        f"👤 Логин: {login}",
        f"📦 Подписка: {status_text}",
        f"⌛ Осталось: {format_time_left(key)}",
    ]
    return "\n".join(lines)


def build_key_card_text(key, user=None) -> str:
    return build_subscription_text(key, user)


def get_owned_key(key_id: int, user_id: int):
    key = get_key_by_id(key_id)
    if not key:
        return None, "Ключ не найден"
    if key["telegram_id"] != user_id:
        return None, "Это не твой ключ"
    return key, None


def validate_connectable_key(key):
    if not key:
        return "Ключ не найден"
    if not get_raw_vless_key(key):
        return "Для этого ключа пока нет сырого VLESS подключения"
    if not is_key_active(key):
        return "Этот ключ неактивен или уже истёк. Продли ключ перед подключением."
    return None


async def render_keys_list(callback: CallbackQuery, answer_text: str | None = None):
    user = get_user(callback.from_user.id)
    if not user:
        if answer_text:
            await callback.answer(answer_text)
        await safe_edit_text(
            callback,
            "🔑 Мои активные ключи\n\n"
            "Пользователь пока не найден в базе.\n"
            "Попробуй сначала нажать /start.",
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
    await render_keys_list(callback, "Список обновлён")


@router.callback_query(F.data.startswith("view_key_"))
async def view_key_handler(callback: CallbackQuery):
    key_id = int(callback.data.removeprefix("view_key_"))
    key, error = get_owned_key(key_id, callback.from_user.id)
    if error:
        await callback.answer(error, show_alert=True)
        return

    await render_key_card(callback, key)


@router.callback_query(F.data.startswith("refresh_key_"))
async def refresh_key_handler(callback: CallbackQuery):
    key_id = int(callback.data.removeprefix("refresh_key_"))
    key, error = get_owned_key(key_id, callback.from_user.id)
    if error:
        await callback.answer(error, show_alert=True)
        return

    await render_key_card(callback, key, "Карточка обновлена")


@router.callback_query(F.data.startswith("extend_key:"))
async def extend_key_handler(callback: CallbackQuery):
    _, key_id_str, days_str = callback.data.split(":")
    key_id = int(key_id_str)
    days = int(days_str)

    key, error = get_owned_key(key_id, callback.from_user.id)
    if error:
        await callback.answer(error, show_alert=True)
        return

    if key["is_trial"]:
        await callback.answer("Пробный ключ продлевать нельзя", show_alert=True)
        return

    extend_key(key_id, days)
    updated_key = get_key_by_id(key_id)
    await render_key_card(callback, updated_key, f"Ключ продлён на {days} дней")


@router.callback_query(F.data.startswith("delete_key_confirm:"))
async def delete_key_handler(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("Нет доступа", show_alert=True)
        return

    key_id = int(callback.data.split(":")[1])
    success, message = await delete_key_completely(key_id)
    if not success:
        await callback.answer(message, show_alert=True)
        return

    await render_keys_list(callback, "Ключ удалён ✅")


@router.callback_query(F.data.startswith("delete_key:"))
async def confirm_delete_key_handler(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("Нет доступа", show_alert=True)
        return

    key_id = int(callback.data.split(":")[1])
    key = get_key_by_id(key_id)
    if not key:
        await callback.answer("Ключ не найден", show_alert=True)
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
        "❗ Ты точно хочешь удалить ключ?\n\n"
        f"🔑 {key['key_name']}\n"
        f"ID: {key_id}",
        reply_markup=kb,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("connect_key_"))
async def connect_key_handler(callback: CallbackQuery):
    key_id = int(callback.data.removeprefix("connect_key_"))
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
        "🚀 Подключение к VPN\n\n"
        "Выбери устройство, на котором будешь использовать VPN:",
        reply_markup=get_device_select_keyboard(key),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("device_"))
async def device_handler(callback: CallbackQuery):
    try:
        device_part, key_id_str = callback.data.split(":", maxsplit=1)
        key_id = int(key_id_str)
    except (ValueError, AttributeError):
        await callback.answer("Некорректные данные подключения", show_alert=True)
        return

    device_code = device_part.removeprefix("device_")

    device_title = DEVICE_TITLES.get(device_code)
    if not device_title:
        await callback.answer("Устройство не поддерживается", show_alert=True)
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
