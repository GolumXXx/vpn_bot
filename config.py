import os

from dotenv import load_dotenv


load_dotenv()


def _parse_admin_ids(raw_value: str) -> list[int]:
    return [
        int(item.strip())
        for item in raw_value.split(",")
        if item.strip().isdigit()
    ]


def _clean_env_value(name: str) -> str | None:
    value = os.getenv(name, "").strip()
    return value or None


BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = _parse_admin_ids(os.getenv("ADMIN_IDS", ""))
SUPPORT_USERNAME = os.getenv("SUPPORT_USERNAME", "your_support_username")
BOT_USERNAME = os.getenv("BOT_USERNAME", "your_bot_username")
SHORT_LINK_BASE_URL = _clean_env_value("SHORT_LINK_BASE_URL")
MANUAL_PAYMENT_URL = _clean_env_value("MANUAL_PAYMENT_URL")
PAYMENT_URL_1M = _clean_env_value("PAYMENT_URL_1M")
PAYMENT_URL_3M = _clean_env_value("PAYMENT_URL_3M")
PAYMENT_URL_6M = _clean_env_value("PAYMENT_URL_6M")
