from database.connection import get_connection


def get_all_telegram_ids() -> list[int]:
    with get_connection() as conn:
        rows = conn.execute("SELECT telegram_id FROM users").fetchall()

    return [row["telegram_id"] for row in rows]
