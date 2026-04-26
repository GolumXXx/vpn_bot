import sqlite3
from contextlib import contextmanager
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "bot.db"
DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"


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
