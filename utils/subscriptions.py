from datetime import datetime

from database.db import is_key_active, parse_datetime
from utils.rows import row_get


def format_key_status(key, *, with_emoji: bool = True) -> str:
    try:
        if is_key_active(key):
            return "✅ активен" if with_emoji else "активен"
    except (IndexError, KeyError, TypeError, ValueError):
        pass

    expires_at = parse_datetime(row_get(key, "expires_at"))
    if expires_at and expires_at <= datetime.now():
        return "⏰ истёк" if with_emoji else "истёк"

    return "❌ отключён" if with_emoji else "неактивен"
