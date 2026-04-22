from aiogram.exceptions import TelegramBadRequest


async def safe_edit_text(message, text: str, reply_markup=None):
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as error:
        if "message is not modified" not in str(error).lower():
            raise
