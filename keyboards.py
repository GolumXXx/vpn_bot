from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

from config import SUPPORT_USERNAME

reply_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Главное меню")]
    ],
    resize_keyboard=True
)

main_inline_menu = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="🎁 Пробный доступ ", callback_data="trial_period")],
        [InlineKeyboardButton(text="💳 Продлить подписк у", callback_data="renew_sub")],
        [InlineKeyboardButton(text="🔑 Мои активные ключи ", callback_data="my_keys")],
        [InlineKeyboardButton(text="🎁 Пригласить друга ", callback_data="invite")],
        [InlineKeyboardButton(text="🌐 Наши сервисы ", callback_data="services")],
        [InlineKeyboardButton(text="🛟 Помощь ", callback_data="help")]
    ]
)

trial_menu = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Получить пробный доступ 🚀", callback_data="get_trial")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_main")]
    ]
)

renew_menu = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="💳 1 месяц — 99 ₽ 💳", callback_data="tariff_1m")],
        [InlineKeyboardButton(text="💳 3 месяца — 189 ₽ 💳", callback_data="tariff_3m")],
        [InlineKeyboardButton(text="💳 12 месяцев — 1299 ₽ 💳", callback_data="tariff_12m")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="payments_back_main")]
    ]
)

help_menu = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="💬 Написать в поддержку ", url="https://t.me/@golumZX")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_main")]
    ]
)

keys_menu = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Обновить", callback_data="my_keys_refresh")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_main")]
    ]
)

invite_menu = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="🔗 Получить ссылку", callback_data="get_invite_link")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_main")]
    ]
)

services_menu = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="🌐 VPN 🌐", callback_data="service_vpn")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_main")]
    ]
)


def get_payment_menu(tariff_code: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💳 Оплатить 💳", callback_data=f"pay_{tariff_code}")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_renew")]
        ]
    )
