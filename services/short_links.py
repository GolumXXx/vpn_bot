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


def get_vless_by_code(code: str | None) -> str | None:
    if not code:
        return None

    with get_connection() as conn:
        init_short_links_schema(conn)
        row = conn.execute(
            "SELECT vless FROM links WHERE code = ?",
            (code.strip(),),
        ).fetchone()

    return row["vless"] if row else None


def get_original_url(code: str) -> str | None:
    return get_vless_by_code(code)


def _extract_code_from_url(short_url: str | None) -> str | None:
    if not short_url:
        return None

    parsed_url = urlparse(short_url.strip())
    if parsed_url.scheme not in ("http", "https"):
        return None

    path_parts = [part for part in parsed_url.path.split("/") if part]
    return path_parts[-1] if path_parts else None


def resolve_vless_link(value: str | None) -> str | None:
    if not value:
        return None

    raw_value = value.strip()
    if raw_value.startswith("vless://"):
        return raw_value

    code = _extract_code_from_url(raw_value)
    if not code:
        return raw_value

    return get_vless_by_code(code) or raw_value


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
    code = _extract_code_from_url(short_url)
    if not code:
        return

    with get_connection() as conn:
        init_short_links_schema(conn)
        conn.execute("DELETE FROM links WHERE code = ?", (code,))
