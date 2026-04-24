from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

from config import SUPPORT_USERNAME


def _build_support_url() -> str:
    username = SUPPORT_USERNAME.removeprefix("@").strip()
    if not username or username == "your_support_username":
        username = "golumZX"
    return f"https://t.me/{username}"


reply_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Главное меню")]
    ],
    resize_keyboard=True
)

main_inline_menu = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="🎁 Попробовать бесплатно", callback_data="trial_period")],
        [InlineKeyboardButton(text="💳 Купить / продлить VPN", callback_data="renew_sub")],
        [InlineKeyboardButton(text="🔑 Мои VPN-ключи", callback_data="my_keys")],
        [InlineKeyboardButton(text="📱 Как подключить VPN", callback_data="services")],
        [InlineKeyboardButton(text="🛟 Поддержка", callback_data="help")]
    ]
)

trial_menu = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Получить пробный доступ", callback_data="get_trial")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_main")]
    ]
)

renew_menu = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="💳 1 месяц — 89 ₽", callback_data="tariff_1m")],
        [InlineKeyboardButton(text="💳 3 месяца — 269 ₽", callback_data="tariff_3m")],
        [InlineKeyboardButton(text="💳 6 месяцев — 549 ₽", callback_data="tariff_6m")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="payments_back_main")]
    ]
)

help_menu = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="💬 Написать в поддержку", url=_build_support_url())],
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
        [InlineKeyboardButton(text="🔑 Открыть мои VPN-ключи", callback_data="service_vpn")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_main")]
    ]
)

payment_done_menu = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="🔑 Мои VPN-ключи", callback_data="my_keys")],
        [InlineKeyboardButton(text="⬅️ В главное меню", callback_data="back_main")]
    ]
)

manual_payment_wait_menu = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="💳 К тарифам", callback_data="back_renew")],
        [InlineKeyboardButton(text="⬅️ В главное меню", callback_data="payments_back_main")]
    ]
)


def get_manual_payment_request_menu(order_id: str, payment_url: str | None = None) -> InlineKeyboardMarkup:
    rows = []

    if payment_url:
        rows.append([InlineKeyboardButton(text="💸 Оплатить через Ozon", url=payment_url)])

    rows.extend(
        [
            [InlineKeyboardButton(text="✅ Я оплатил", callback_data=f"manual_payment_paid:{order_id}")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_renew")],
        ]
    )

    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_manual_payment_waiting_menu(payment_url: str | None = None) -> InlineKeyboardMarkup:
    rows = []

    if payment_url:
        rows.append([InlineKeyboardButton(text="💳 Открыть оплату", url=payment_url)])

    rows.extend(manual_payment_wait_menu.inline_keyboard)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_payment_menu(tariff_code: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💳 Создать заявку", callback_data=f"pay_{tariff_code}")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_renew")]
        ]
    )


def get_manual_payment_admin_menu(order_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Подтвердить оплату", callback_data=f"approve_manual_payment:{order_id}")]
        ]
    )


admin_menu = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="📊 Дашборд", callback_data="admin_dashboard")],
        [InlineKeyboardButton(text="💰 Ожидающие оплаты", callback_data="admin_payments")],
        [InlineKeyboardButton(text="🔍 Поиск пользователей", callback_data="admin_search")],
        [InlineKeyboardButton(text="⚙️ Настройки", callback_data="admin_settings")],
        [InlineKeyboardButton(text="❌ Закрыть панель", callback_data="admin_close")],
    ]
)

admin_back_menu = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_menu")],
        [InlineKeyboardButton(text="❌ Закрыть панель", callback_data="admin_close")],
    ]
)


def get_admin_pending_payments_menu(payments) -> InlineKeyboardMarkup:
    rows = []

    for payment in payments:
        if payment["status"] == "waiting_admin_confirmation":
            rows.append(
                [
                    InlineKeyboardButton(
                        text=f"✅ Подтвердить {payment['order_id']}",
                        callback_data=f"approve_manual_payment:{payment['order_id']}",
                    )
                ]
            )

    rows.extend(admin_back_menu.inline_keyboard)
    return InlineKeyboardMarkup(inline_keyboard=rows)
