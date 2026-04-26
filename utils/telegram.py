import logging

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery

from texts.common import GENERIC_ERROR_TEXT


logger = logging.getLogger(__name__)


async def safe_edit_text(message_or_callback, text: str, reply_markup=None):
    callback = message_or_callback if isinstance(message_or_callback, CallbackQuery) else None
    message = callback.message if callback else message_or_callback

    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as error:
        if "message is not modified" in str(error).lower():
            return
        logger.exception("Failed to edit Telegram message")
        if callback:
            await callback.answer(GENERIC_ERROR_TEXT, show_alert=True)
        else:
            raise
    except Exception:
        logger.exception("Unexpected error while editing Telegram message")
        if callback:
            await callback.answer(GENERIC_ERROR_TEXT, show_alert=True)
        else:
            raise
