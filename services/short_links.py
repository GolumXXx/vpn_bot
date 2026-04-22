import os
import secrets
import sqlite3
import string
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "bot.db"
DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"
SHORT_CODE_ALPHABET = string.ascii_letters + string.digits
SHORT_CODE_LENGTH = 8


load_dotenv(BASE_DIR / ".env")

# services/short_links.py
short_links = {
    "abc123": "https://t.me/your_bot"
}

def get_original_url(code: str) -> str | None:
    return short_links.get(code)

def create_short_link(original_url: str, user_id: int = None, link_type: str = None) -> str:
    code = "abc123"  # можно заменить генерацией
    short_links[code] = original_url
    return f"http://127.0.0.1:8000/{code}"


@contextmanager
def get_connection():
    conn = sqlite3.connect(DB_PATH, timeout=30, cached_statements=128)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        conn.execute("PRAGMA busy_timeout = 30000")
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_short_links_schema(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            vless TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_links_code
        ON links (code)
        """
    )


def _format_datetime(value: datetime) -> str:
    return value.strftime(DATETIME_FORMAT)


def _normalize_base_url(value: str | None) -> str | None:
    if not value:
        return None
    return value.strip().rstrip("/")


def generate_short_code(length: int = SHORT_CODE_LENGTH) -> str:
    return "".join(secrets.choice(SHORT_CODE_ALPHABET) for _ in range(length))


def create_short_link(vless_link: str, base_url: str | None = None) -> str:
    if not vless_link or not vless_link.strip():
        raise ValueError("vless_link не может быть пустым")

    normalized_base_url = _normalize_base_url(
        base_url or os.getenv("SHORT_LINK_BASE_URL")
    )
    if not normalized_base_url:
        return vless_link

    with get_connection() as conn:
        init_short_links_schema(conn)

        for _ in range(10):
            code = generate_short_code()
            try:
                conn.execute(
                    """
                    INSERT INTO links (code, vless, created_at)
                    VALUES (?, ?, ?)
                    """,
                    (code, vless_link.strip(), _format_datetime(datetime.now())),
                )
                return f"{normalized_base_url}/{code}"
            except sqlite3.IntegrityError:
                continue

    raise RuntimeError("Не удалось создать уникальный короткий код")


def delete_short_link_by_url(short_url: str | None):
    if not short_url:
        return

    parsed_url = urlparse(short_url)
    if parsed_url.scheme not in ("http", "https"):
        return

    code = parsed_url.path.strip("/")
    if not code:
        return

    with get_connection() as conn:
        init_short_links_schema(conn)
        conn.execute("DELETE FROM links WHERE code = ?", (code,))
