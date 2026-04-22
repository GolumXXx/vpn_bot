import sqlite3

telegram_id = 7066754428  # твой Telegram ID

conn = sqlite3.connect("bot.db")
cursor = conn.cursor()

cursor.execute(
    "DELETE FROM vpn_keys WHERE telegram_id = ?",
    (telegram_id,)
)

deleted_count = cursor.rowcount

conn.commit()
conn.close()

print(f"Удалено ключей: {deleted_count}")