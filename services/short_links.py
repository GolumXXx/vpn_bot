import secrets
import sqlite3
from datetime import datetime
from urllib.parse import urlparse

from config import SHORT_LINK_BASE_URL
from database.connection import DATETIME_FORMAT, get_connection

SAFE_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"
SHORT_CODE_LENGTH = 8


def init_short_links_schema(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            url TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    columns = _table_columns(conn)
    if "url" not in columns:
        conn.execute("ALTER TABLE links ADD COLUMN url TEXT")
        columns.add("url")
    if "vless" not in columns:
        conn.execute("ALTER TABLE links ADD COLUMN vless TEXT")
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_links_code
        ON links (code)
        """
    )


def _table_columns(conn) -> set[str]:
    return {
        row["name"]
        for row in conn.execute("PRAGMA table_info(links)").fetchall()
    }


def _link_select_expression(conn) -> str | None:
    columns = _table_columns(conn)
    if "url" in columns and "vless" in columns:
        return "COALESCE(url, vless)"
    if "url" in columns:
        return "url"
    if "vless" in columns:
        return "vless"
    return None


def _format_datetime(value: datetime) -> str:
    return value.strftime(DATETIME_FORMAT)


def _normalize_base_url(value: str | None) -> str | None:
    if not value:
        return None
    return value.strip().rstrip("/")


def generate_code(length: int = SHORT_CODE_LENGTH) -> str:
    if length <= 0:
        raise ValueError("length должен быть больше 0")
    return "".join(secrets.choice(SAFE_CHARS) for _ in range(length))


def code_exists(conn, code: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM links WHERE code = ? LIMIT 1",
        (code,),
    ).fetchone()
    return row is not None


def find_existing_code(conn, vless_link: str) -> str | None:
    value_expression = _link_select_expression(conn)
    if not value_expression:
        return None

    row = conn.execute(
        f"""
        SELECT code
        FROM links
        WHERE {value_expression} = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (vless_link,),
    ).fetchone()
    return row["code"] if row else None


def insert_short_link(conn, code: str, vless_link: str):
    columns = _table_columns(conn)
    created_at = _format_datetime(datetime.now())

    if "url" in columns and "vless" in columns:
        conn.execute(
            """
            INSERT INTO links (code, url, vless, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (code, vless_link, vless_link, created_at),
        )
        return

    if "url" in columns:
        conn.execute(
            """
            INSERT INTO links (code, url, created_at)
            VALUES (?, ?, ?)
            """,
            (code, vless_link, created_at),
        )
        return

    if "vless" in columns:
        conn.execute(
            """
            INSERT INTO links (code, vless, created_at)
            VALUES (?, ?, ?)
            """,
            (code, vless_link, created_at),
        )
        return

    raise RuntimeError("В таблице links нет колонки url или vless")


def get_vless_by_code(code: str | None) -> str | None:
    if not code:
        return None

    with get_connection() as conn:
        init_short_links_schema(conn)
        value_expression = _link_select_expression(conn)
        if not value_expression:
            return None

        row = conn.execute(
            f"SELECT {value_expression} AS url FROM links WHERE code = ?",
            (code.strip(),),
        ).fetchone()

    return row["url"] if row else None


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
        base_url or SHORT_LINK_BASE_URL
    )
    if not normalized_base_url:
        return vless_link
    short_base_url = (
        normalized_base_url
        if normalized_base_url.endswith("/s")
        else f"{normalized_base_url}/s"
    )

    with get_connection() as conn:
        init_short_links_schema(conn)
        existing_code = find_existing_code(conn, vless_link.strip())
        if existing_code:
            return f"{short_base_url}/{existing_code}"

        for _ in range(50):
            code = generate_code()
            if code_exists(conn, code):
                continue
            try:
                insert_short_link(conn, code, vless_link.strip())
                return f"{short_base_url}/{code}"
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
