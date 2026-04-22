import logging
import re
import sqlite3
from datetime import datetime
from pathlib import Path

from flask import Flask, redirect, request


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "bot.db"
DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
CODE_RE = re.compile(r"^[A-Za-z0-9]{6,8}$")


def get_connection():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def init_db():
    with get_connection() as conn:
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
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS link_clicks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL,
                ip TEXT,
                user_agent TEXT,
                clicked_at TEXT NOT NULL
            )
            """
        )
        conn.commit()


def find_vless_link(code: str) -> str | None:
    if not code or not CODE_RE.fullmatch(code):
        return None

    with get_connection() as conn:
        row = conn.execute(
            "SELECT vless FROM links WHERE code = ?",
            (code,),
        ).fetchone()

    if not row:
        return None

    return row["vless"]


def log_click(code: str):
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO link_clicks (code, ip, user_agent, clicked_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                code,
                request.headers.get("X-Forwarded-For", request.remote_addr),
                request.headers.get("User-Agent", ""),
                datetime.now().strftime(DATETIME_FORMAT),
            ),
        )
        conn.commit()


@app.get("/")
def index():
    return "VPN short links service"


@app.get("/<code>")
def open_short_link(code: str):
    vless_link = find_vless_link(code.strip())
    if not vless_link:
        return "Link not found", 404

    app.logger.info("Redirect short link %s", code)
    log_click(code)
    return redirect(vless_link, code=302)


init_db()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
