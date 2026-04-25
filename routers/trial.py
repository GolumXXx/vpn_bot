import logging

from aiogram import Router, F
from aiogram.types import CallbackQuery

from database.db import add_or_update_user, has_used_trial, create_trial_key
from keyboards import trial_menu
from routers.ui import safe_edit_text
from services.xui_client import XUIError

router = Router()
logger = logging.getLogger(__name__)


@router.callback_query(F.data == "trial_period")
async def trial_period_handler(callback: CallbackQuery):
    await safe_edit_text(
        callback.message,
        "🎁 Попробовать бесплатно\n\n"
        "7 дней бесплатно для проверки VPN.\n\n"
        "Нажми кнопку ниже, чтобы получить доступ.",
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
        await callback.answer("Пробный доступ уже использован", show_alert=True)
        return

    try:
        key = await create_trial_key(
            telegram_id=user.id,
            username=user.username,
            first_name=user.first_name,
        )
        logger.info("Created trial VPN key: user_id=%s", user.id)

        await callback.answer("Пробный доступ готов ✅", show_alert=True)
        await callback.message.answer(
            "✅ Пробный доступ готов\n\n"
            "Открой «Мои VPN-ключи», чтобы подключиться."
        )

    except XUIError:
        logger.exception("XUI error during trial key creation: user_id=%s", user.id)
        await callback.answer(
            "Не удалось выдать VPN-ключ. Попробуй позже или обратись в поддержку.",
            show_alert=True,
        )

    except Exception:
        logger.exception("Unexpected trial key creation error: user_id=%s", user.id)
        await callback.answer(
            "Что-то пошло не так 😕\n\nПопробуй ещё раз или обратись в поддержку.",
            show_alert=True,
        )
