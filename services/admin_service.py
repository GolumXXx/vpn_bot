import asyncio
import logging


logger = logging.getLogger(__name__)


async def send_broadcast(bot, user_ids: list[int], text: str, delay_seconds: float = 0.05) -> int:
    sent_count = 0
    for user_id in user_ids:
        try:
            await bot.send_message(user_id, text)
            sent_count += 1
        except Exception:
            logger.exception("Failed to send admin broadcast message: user_id=%s", user_id)
        await asyncio.sleep(delay_seconds)

    return sent_count
