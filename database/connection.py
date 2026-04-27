import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "bot.db"
DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"
SQLITE_TIMEOUT_SECONDS = 30
SQLITE_BUSY_TIMEOUT_MS = SQLITE_TIMEOUT_SECONDS * 1000

_DATABASE_PRAGMAS_INITIALIZED = False
_DATABASE_PRAGMAS_LOCK = threading.Lock()


def _initialize_database_pragmas(conn):
    global _DATABASE_PRAGMAS_INITIALIZED

    if _DATABASE_PRAGMAS_INITIALIZED:
        return

    with _DATABASE_PRAGMAS_LOCK:
        if _DATABASE_PRAGMAS_INITIALIZED:
            return

        conn.execute("PRAGMA journal_mode = WAL")
        _DATABASE_PRAGMAS_INITIALIZED = True


@contextmanager
def get_connection():
    conn = sqlite3.connect(
        DB_PATH,
        timeout=SQLITE_TIMEOUT_SECONDS,
        cached_statements=256,
    )
    conn.row_factory = sqlite3.Row
    try:
        _initialize_database_pragmas(conn)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA synchronous = NORMAL")
        conn.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS}")
        conn.execute("PRAGMA temp_store = MEMORY")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
