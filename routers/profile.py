from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from datetime import datetime
from database.db import (
    get_user,
    get_user_key_stats,
    parse_datetime,
)
from routers.ui import safe_edit_text

router = Router()


profile_menu = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Обновить", callback_data="profile_refresh")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_main")]
    ]
)

def build_profile_text(user) -> str:
    now = datetime.now()
    username = f"@{user['username']}" if user["username"] else "нет"

    key_stats = get_user_key_stats(user["telegram_id"])

    lines = [
        "👤 Профиль",
        "",
        f"🆔 ID: {user['telegram_id']}",
        f"👤 Имя: {user['first_name'] or '—'}",
        f"📛 Username: {username}",
    ]

    # Показываем trial только если он ещё активен
    if user["used_trial"]:
        trial_date = parse_datetime(user["trial_activated_at"])

        if trial_date:
            diff = now - trial_date

            # меньше 24 часов
            if diff.total_seconds() < 86400:
                lines.append("")
                lines.append("🎁 Пробный период: активен")
                lines.append(f"🕒 Дата активации: {user['trial_activated_at']}")

    lines.extend([
        "",
        "🔑 Ключи:",
        f"• Всего ключей: {key_stats['total_keys']}",
        f"• Активных ключей: {key_stats['active_keys']}",
    ])

    return "\n".join(lines)


@router.callback_query(F.data == "profile")
async def profile_handler(callback: CallbackQuery):
    user = get_user(callback.from_user.id)

    if not user:
        await safe_edit_text(
            callback.message,
            "👤 Профиль\n\n"
            "Пользователь пока не найден в базе.\n"
            "Нажми /start, чтобы бот тебя сохранил.",
            reply_markup=profile_menu
        )
        await callback.answer()
        return

    await safe_edit_text(
        callback.message,
        build_profile_text(user),
        reply_markup=profile_menu
    )
    await callback.answer()


@router.callback_query(F.data == "profile_refresh")
async def profile_refresh_handler(callback: CallbackQuery):
    user = get_user(callback.from_user.id)

    if not user:
        await callback.answer("Пользователь не найден", show_alert=True)
        return

    await safe_edit_text(
        callback.message,
        build_profile_text(user),
        reply_markup=profile_menu
    )
    await callback.answer("Профиль обновлён")
