import os

from dotenv import load_dotenv


load_dotenv()


def _parse_admin_ids(raw_value: str) -> list[int]:
    return [
        int(item.strip())
        for item in raw_value.split(",")
        if item.strip().isdigit()
    ]


BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = _parse_admin_ids(os.getenv("ADMIN_IDS", ""))
SUPPORT_USERNAME = os.getenv("SUPPORT_USERNAME", "your_support_username")
BOT_USERNAME = os.getenv("BOT_USERNAME", "your_bot_username")
SHORT_LINK_BASE_URL = os.getenv("SHORT_LINK_BASE_URL")
