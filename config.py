import os

from dotenv import load_dotenv
from utils.env import parse_admin_ids


load_dotenv()


def _clean_env_value(name: str) -> str | None:
    value = os.getenv(name, "").strip()
    return value or None


def _clean_env_int(name: str, default: int | None = None) -> int | None:
    value = _clean_env_value(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


BOT_TOKEN = os.getenv("BOT_TOKEN")
DB_PATH = _clean_env_value("DB_PATH") or "/opt/vpn_bot/vpn_bot/bot.db"
ADMIN_IDS = parse_admin_ids(os.getenv("ADMIN_IDS", ""))
SUPPORT_USERNAME = os.getenv("SUPPORT_USERNAME", "your_support_username")
BOT_USERNAME = os.getenv("BOT_USERNAME", "your_bot_username")
SHORT_LINK_BASE_URL = _clean_env_value("SHORT_LINK_BASE_URL")
SHORTENER_PUBLIC_BASE_URL = _clean_env_value("SHORTENER_PUBLIC_BASE_URL") or SHORT_LINK_BASE_URL
PANEL_URL = _clean_env_value("PANEL_URL")
PANEL_PATH = _clean_env_value("PANEL_PATH")
PANEL_LOGIN = _clean_env_value("PANEL_LOGIN")
PANEL_PASSWORD = _clean_env_value("PANEL_PASSWORD")
MANUAL_PAYMENT_URL = _clean_env_value("MANUAL_PAYMENT_URL")
PAYMENT_URL_1M = _clean_env_value("PAYMENT_URL_1M")
PAYMENT_URL_3M = _clean_env_value("PAYMENT_URL_3M")
PAYMENT_URL_6M = _clean_env_value("PAYMENT_URL_6M")
PLATEGA_API_BASE_URL = _clean_env_value("PLATEGA_API_BASE_URL") or "https://app.platega.io"
PLATEGA_MERCHANT_ID = _clean_env_value("PLATEGA_MERCHANT_ID")
PLATEGA_API_KEY = _clean_env_value("PLATEGA_API_KEY")
PLATEGA_RETURN_URL = _clean_env_value("PLATEGA_RETURN_URL") or "https://golum.shop/success"
PLATEGA_FAILED_URL = _clean_env_value("PLATEGA_FAILED_URL") or "https://golum.shop/fail"
PLATEGA_PAYMENT_METHOD = _clean_env_int("PLATEGA_PAYMENT_METHOD", 2)
