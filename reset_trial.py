import sqlite3

telegram_id = 7066754428  # твой ID

conn = sqlite3.connect("bot.db")
cursor = conn.cursor()

cursor.execute(
    """
    UPDATE users
    SET used_trial = 0,
        trial_activated_at = NULL
    WHERE telegram_id = ?
    """,
    (telegram_id,)
)

conn.commit()
conn.close()

print("Пробный период сброшен")