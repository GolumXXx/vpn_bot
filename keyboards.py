from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

from config import ADMIN_IDS, SUPPORT_USERNAME


ADMIN_ID_SET = set(ADMIN_IDS)


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

def get_main_inline_menu(user_id: int | None = None) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="🎁 Попробовать бесплатно", callback_data="trial_period")],
        [InlineKeyboardButton(text="💳 Купить / продлить VPN", callback_data="renew_sub")],
        [InlineKeyboardButton(text="🔑 Мои VPN-ключи", callback_data="my_keys")],
        [InlineKeyboardButton(text="📱 Как подключить VPN", callback_data="services")],
        [InlineKeyboardButton(text="🛟 Поддержка", callback_data="help")],
    ]

    if user_id in ADMIN_ID_SET:
        rows.append([InlineKeyboardButton(text="⚙️ Админ-панель", callback_data="admin_menu")])

    return InlineKeyboardMarkup(inline_keyboard=rows)


main_inline_menu = get_main_inline_menu()

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
        [
            InlineKeyboardButton(
                text="📜 Пользовательское соглашение",
                url="https://telegra.ph/Polzovatelskoe-soglashenie-04-25-43",
            )
        ],
        [
            InlineKeyboardButton(
                text="📄 Политика конфиденциальности",
                url="https://telegra.ph/Politika-konfidencialnosti-04-25-30",
            )
        ],
        [InlineKeyboardButton(text="⬅️ В главное меню", callback_data="back_main")]
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

    rows.append([InlineKeyboardButton(text="❌ Отменить заявку", callback_data=f"cancel_manual_payment:{order_id}")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back_renew")])

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
        [InlineKeyboardButton(text="🔑 Управление ключами", callback_data="admin_keys")],
        [InlineKeyboardButton(text="📜 Логи", callback_data="admin_logs")],
        [InlineKeyboardButton(text="🔍 Поиск пользователей", callback_data="admin_search")],
        [InlineKeyboardButton(text="⚙️ Настройки", callback_data="admin_settings")],
        [InlineKeyboardButton(text="❌ Закрыть панель", callback_data="admin_close")],
    ]
)

admin_back_menu = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад в админ-панель", callback_data="admin_menu")],
        [InlineKeyboardButton(text="❌ Закрыть панель", callback_data="admin_close")],
    ]
)

admin_logs_menu = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Обновить", callback_data="admin_logs")],
        [InlineKeyboardButton(text="⬅️ Назад в админ-панель", callback_data="admin_menu")],
    ]
)


def get_admin_pending_payments_menu(payments) -> InlineKeyboardMarkup:
    rows = []

    for payment in payments:
        telegram_id = payment["telegram_id"]

        if payment["status"] == "waiting_admin_confirmation":
            rows.append(
                [
                    InlineKeyboardButton(
                        text="✅ Подтвердить оплату",
                        callback_data=f"approve_manual_payment:{payment['order_id']}",
                    )
                ]
            )

        if payment["status"] == "pending_receipt":
            rows.extend(
                [
                    [
                        InlineKeyboardButton(
                            text="✉️ Напомнить о чеке",
                            callback_data=f"admin_remind_payment:{payment['order_id']}",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="❌ Отменить заявку",
                            callback_data=f"admin_cancel_payment:{payment['order_id']}",
                        )
                    ],
                ]
            )

        rows.append(
            [
                InlineKeyboardButton(
                    text="🔑 Открыть пользователя",
                    callback_data=f"admin_user_keys:{telegram_id}",
                )
            ]
        )

    rows.extend(admin_back_menu.inline_keyboard)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_admin_user_keys_menu(keys) -> InlineKeyboardMarkup:
    rows = []

    for key in keys:
        key_id = key["id"]
        rows.extend(
            [
                [InlineKeyboardButton(text="📅 Продлить на 30 дней", callback_data=f"admin_extend_key:{key_id}")],
                [InlineKeyboardButton(text="🗑 Удалить ключ", callback_data=f"admin_delete_key:{key_id}")],
            ]
        )

    rows.extend(admin_back_menu.inline_keyboard)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_admin_delete_key_confirm_menu(key_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"admin_delete_key_confirm:{key_id}")],
            [InlineKeyboardButton(text="⬅️ Отмена", callback_data=f"admin_key:{key_id}")],
        ]
    )
