from aiogram import Router, F
from aiogram.types import CallbackQuery

from database.db import add_or_update_user, has_used_trial, create_trial_key
from keyboards import trial_menu
from routers.ui import safe_edit_text
from services.xui_client import XUIError

router = Router()


@router.callback_query(F.data == "trial_period")
async def trial_period_handler(callback: CallbackQuery):
    await safe_edit_text(
        callback.message,
        "🔑 Пробный период\n\n"
        "Что даёт пробный доступ:\n"
        "• 1 день бесплатно\n"
        "• только 1 раз на пользователя\n"
        "• без продления\n\n"
        "Нажми кнопку ниже:",
        reply_markup=trial_menu
    )
    await callback.answer()


@router.callback_query(F.data == "get_trial")
async def get_trial_handler(callback: CallbackQuery):
    user = callback.from_user

    add_or_update_user(
        telegram_id=user.id,
        username=user.username,
        first_name=user.first_name,
    )

    if has_used_trial(user.id):
        await callback.answer("Ты уже использовал пробный период", show_alert=True)
        return

    try:
        key = await create_trial_key(
            telegram_id=user.id,
            username=user.username,
            first_name=user.first_name,
        )

        await callback.answer("Пробный доступ выдан ✅", show_alert=True)
        await callback.message.answer(
            f"✅ Пробный ключ создан\n\nВот твой ключ:\n{key}"
        )

    except XUIError as e:
        await callback.answer(f"Ошибка панели: {e}", show_alert=True)

    except Exception as e:
        await callback.answer(f"Неожиданная ошибка: {e}", show_alert=True)
