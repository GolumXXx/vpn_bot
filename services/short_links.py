import secrets
import sqlite3
import re
from datetime import datetime
from urllib.parse import urlparse

from config import SHORT_LINK_BASE_URL
from database.connection import DATETIME_FORMAT, get_connection

SAFE_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"
SHORT_CODE_LENGTH = 8
MAX_SHORT_CODE_LENGTH = 32
CODE_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")


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
        columns.add("vless")
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_links_code
        ON links (code)
        """
    )
    if "url" in columns:
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_links_url
            ON links (url)
            """
        )
    if "vless" in columns:
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_links_vless
            ON links (vless)
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
        return "COALESCE(NULLIF(vless, ''), NULLIF(url, ''))"
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


def normalize_code(code: str | None) -> str | None:
    if not code:
        return None

    normalized_code = str(code).strip()
    if not normalized_code:
        return None
    if len(normalized_code) > MAX_SHORT_CODE_LENGTH:
        return None
    if not CODE_PATTERN.fullmatch(normalized_code):
        return None
    return normalized_code


def generate_code(length: int = SHORT_CODE_LENGTH) -> str:
    if length <= 0:
        raise ValueError("length должен быть больше 0")
    if length > MAX_SHORT_CODE_LENGTH:
        raise ValueError("length не может быть больше 32")
    return "".join(secrets.choice(SAFE_CHARS) for _ in range(length))


def code_exists(conn, code: str) -> bool:
    normalized_code = normalize_code(code)
    if not normalized_code:
        return False

    row = conn.execute(
        "SELECT 1 FROM links WHERE code = ? LIMIT 1",
        (normalized_code,),
    ).fetchone()
    return row is not None


def find_existing_code(conn, vless_link: str) -> str | None:
    columns = _table_columns(conn)
    conditions = []
    params = []

    if "vless" in columns:
        conditions.append("vless = ?")
        params.append(vless_link)
    if "url" in columns:
        conditions.append("url = ?")
        params.append(vless_link)

    if not conditions:
        return None

    row = conn.execute(
        f"""
        SELECT code
        FROM links
        WHERE {" OR ".join(conditions)}
        ORDER BY id DESC
        LIMIT 1
        """,
        params,
    ).fetchone()
    return row["code"] if row else None


def insert_short_link(conn, code: str, vless_link: str):
    columns = _table_columns(conn)
    created_at = _format_datetime(datetime.now())
    normalized_code = normalize_code(code)
    normalized_vless_link = vless_link.strip()

    if not normalized_code:
        raise ValueError("Некорректный короткий код")

    if "url" in columns and "vless" in columns:
        conn.execute(
            """
            INSERT INTO links (code, url, vless, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                normalized_code,
                normalized_vless_link,
                normalized_vless_link,
                created_at,
            ),
        )
        return

    if "url" in columns:
        conn.execute(
            """
            INSERT INTO links (code, url, created_at)
            VALUES (?, ?, ?)
            """,
            (normalized_code, normalized_vless_link, created_at),
        )
        return

    if "vless" in columns:
        conn.execute(
            """
            INSERT INTO links (code, vless, created_at)
            VALUES (?, ?, ?)
            """,
            (normalized_code, normalized_vless_link, created_at),
        )
        return

    raise RuntimeError("В таблице links нет колонки url или vless")


def get_vless_by_code(code: str | None) -> str | None:
    normalized_code = normalize_code(code)
    if not normalized_code:
        return None

    with get_connection() as conn:
        init_short_links_schema(conn)
        value_expression = _link_select_expression(conn)
        if not value_expression:
            return None

        row = conn.execute(
            f"SELECT {value_expression} AS url FROM links WHERE code = ?",
            (normalized_code,),
        ).fetchone()

    return row["url"].strip() if row and row["url"] else None


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

    normalized_vless_link = vless_link.strip()
    normalized_base_url = _normalize_base_url(
        base_url or SHORT_LINK_BASE_URL
    )
    if not normalized_base_url:
        return normalized_vless_link
    short_base_url = (
        normalized_base_url
        if normalized_base_url.endswith("/s")
        else f"{normalized_base_url}/s"
    )

    with get_connection() as conn:
        init_short_links_schema(conn)
        existing_code = find_existing_code(conn, normalized_vless_link)
        if existing_code:
            return f"{short_base_url}/{existing_code}"

        for _ in range(50):
            code = generate_code()
            if code_exists(conn, code):
                continue
            try:
                insert_short_link(conn, code, normalized_vless_link)
                return f"{short_base_url}/{code}"
            except sqlite3.IntegrityError:
                continue

    raise RuntimeError("Не удалось создать уникальный короткий код")


def delete_short_link_by_url(short_url: str | None):
    raw_value = short_url.strip() if short_url else None
    if not raw_value:
        return

    with get_connection() as conn:
        init_short_links_schema(conn)
        if raw_value.startswith("vless://"):
            columns = _table_columns(conn)
            conditions = []
            params = []

            if "vless" in columns:
                conditions.append("vless = ?")
                params.append(raw_value)
            if "url" in columns:
                conditions.append("url = ?")
                params.append(raw_value)

            if conditions:
                conn.execute(
                    f"DELETE FROM links WHERE {' OR '.join(conditions)}",
                    params,
                )
            return

        code = normalize_code(_extract_code_from_url(raw_value))
        if code:
            conn.execute("DELETE FROM links WHERE code = ?", (code,))
