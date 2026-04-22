import os
from datetime import datetime

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
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
            ("Happ (Google Play)", "https://play.google.com/store/apps/details?id=com.happproxy&hl=ru"),
            ("APK (если не работает Play)", "https://github.com/2dust/v2rayNG/releases"),
        ],
        "steps": [
            "Установи приложение (кнопка ниже)",
            "Открой приложение",
            'Нажми "+" -> Import from clipboard',
            "Вставь ключ",
        ],
    },
    "ios": {
        "apps": [
            ("v2rayTun", "https://apps.apple.com/app/v2raytun/id6476628951"),
            ("Happ", "https://apps.apple.com/app/happ-proxy-utility/id6504287215"),
        ],
        "steps": [
            "Установи приложение",
            "Открой приложение",
            'Нажми "Add config"',
            "Вставь ключ",
        ],
    },
    "windows": {
        "apps": [
            ("Скачать v2rayN", "https://github.com/2dust/v2rayN/releases"),
        ],
        "steps": [
            "Скачай v2rayN (кнопка ниже)",
            "Распакуй архив",
            "Запусти v2rayN.exe",
            'Нажми "Import from clipboard"',
            "Вставь ключ и нажми Start",
        ],
    },
    "mac": {
        "apps": [
            ("v2rayTun", "https://apps.apple.com/app/v2raytun/id6476628951"),
        ],
        "steps": [
            "Установи v2rayTun",
            "Открой приложение",
            "Добавь конфигурацию",
            "Вставь ключ",
        ],
    },
}


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


def get_keys_list_keyboard(keys):
    buttons = []

    for key in keys:
        status_emoji = "✅" if is_key_active(key) else "⏰"
        trial_mark = " (trial)" if key["is_trial"] else ""
        buttons.append(
            [
                InlineKeyboardButton(
                    text=f"{status_emoji} {key['key_name']}{trial_mark}",
                    callback_data=f"view_key_{key['id']}",
                )
            ]
        )

    buttons.extend(
        [
            [InlineKeyboardButton(text="🔄 Обновить", callback_data="my_keys_refresh")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_main")],
        ]
    )

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_key_card_keyboard(key, user_id):
    buttons = [
        [
            InlineKeyboardButton(
                text="🚀 Подключить VPN",
                callback_data=f"connect_key_{key['id']}",
            )
        ]
    ]

    if not key["is_trial"]:
        buttons.extend(
            [
                [
                    InlineKeyboardButton(
                        text="📅 +30 дней",
                        callback_data=f"extend_key:{key['id']}:30",
                    ),
                    InlineKeyboardButton(
                        text="📅 +90 дней",
                        callback_data=f"extend_key:{key['id']}:90",
                    ),
                ],
                [
                    InlineKeyboardButton(
                        text="📅 +365 дней",
                        callback_data=f"extend_key:{key['id']}:365",
                    )
                ],
            ]
        )

    if user_id in ADMIN_IDS:
        buttons.append(
            [
                InlineKeyboardButton(
                    text="🗑 Удалить ключ",
                    callback_data=f"delete_key:{key['id']}",
                )
            ]
        )

    buttons.extend(
        [
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="my_keys")],
            [InlineKeyboardButton(text="🔄 Обновить", callback_data=f"refresh_key_{key['id']}")],
        ]
    )

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_device_select_keyboard(key_id):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🤖 Android", callback_data=f"device_android:{key_id}"),
                InlineKeyboardButton(text="🍎 iPhone", callback_data=f"device_ios:{key_id}"),
            ],
            [
                InlineKeyboardButton(text="💻 Mac", callback_data=f"device_mac:{key_id}"),
                InlineKeyboardButton(text="🪟 Windows", callback_data=f"device_windows:{key_id}"),
            ],
            [
                InlineKeyboardButton(text="⬅️ Назад к ключу", callback_data=f"view_key_{key_id}")
            ],
        ]
    )


def get_connect_app_keyboard(key_id, device_code):
    device_config = DEVICE_CONFIGS.get(device_code)
    app_buttons = [
        InlineKeyboardButton(text=title, url=url)
        for title, url in device_config["apps"]
    ]

    return InlineKeyboardMarkup(
        inline_keyboard=[
            app_buttons,
            [
                InlineKeyboardButton(
                    text="⬅️ Назад к устройствам",
                    callback_data=f"connect_key_{key_id}"
                )
            ]
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
        f"{instruction}\n\n"
        f"Твой ключ:\n{key['key_value']}"
    )


def build_keys_list_text(user, keys) -> str:
    username = f"@{user['username']}" if user["username"] else "нет"

    lines = [
        "🔑 Мои активные ключи",
        "",
        f"👤 Имя: {user['first_name'] or '—'}",
        f"📛 Username: {username}",
    ]

    if user["used_trial"] and user["trial_activated_at"]:
        activated_at = parse_datetime(user["trial_activated_at"])
        if activated_at and (datetime.now() - activated_at).total_seconds() < 86400:
            lines.append("🎁 Пробный период: активен")
            lines.append(f"🕒 Дата активации: {user['trial_activated_at']}")

    lines.append("")

    if not keys:
        lines.append("У тебя пока нет ключей.")
        return "\n".join(lines)

    lines.extend(
        [
            f"Всего ключей: {len(keys)}",
            "",
            "Выбери ключ ниже 👇",
        ]
    )
    return "\n".join(lines)


def build_key_card_text(key) -> str:
    panel_email = key["panel_email"] or "—"
    client_uuid = key["client_uuid"] or "—"
    server_id = key["server_id"] or "—"
    inbound_id = key["panel_inbound_id"] or "—"

    lines = [
        f"🔑 {key['key_name']}",
        "",
        f"📌 ID ключа: {key['id']}",
        f"📊 Статус: {format_key_status(key)}",
        f"🎁 Пробный: {'Да' if key['is_trial'] else 'Нет'}",
        f"🕒 Создан: {key['created_at']}",
        f"⏳ Истекает: {key['expires_at'] or '—'}",
        f"⌛ Осталось: {format_time_left(key)}",
        "",
        "🛠 Технические данные ключа:",
        f"🖥 Server ID: {server_id}",
        f"📡 Inbound ID: {inbound_id}",
        f"📧 Panel email: {panel_email}",
        f"🆔 UUID: {client_uuid}",
    ]

    if key["key_value"]:
        lines.extend(["", "🔐 Ключ:", f"{key['key_value']}"])
    else:
        lines.extend(["", "ℹ️ Подключение для этого ключа ещё не собрано в готовую ссылку."])

    return "\n".join(lines)


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
    if not key["key_value"]:
        return "Для этого ключа пока нет готовой ссылки подключения"
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

    keys = get_user_keys(callback.from_user.id)
    await safe_edit_text(
        callback,
        build_keys_list_text(user, keys),
        reply_markup=get_keys_list_keyboard(keys),
    )
    if answer_text:
        await callback.answer(answer_text)
    else:
        await callback.answer()


async def render_key_card(callback: CallbackQuery, key, answer_text: str | None = None):
    await safe_edit_text(
        callback,
        build_key_card_text(key),
        reply_markup=get_key_card_keyboard(key, callback.from_user.id),
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
        reply_markup=get_device_select_keyboard(key["id"]),
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
        reply_markup=get_connect_app_keyboard(key["id"], device_code),
    )
    await callback.answer()
