import sqlite3

telegram_id = 7066754428

conn = sqlite3.connect("bot.db")
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

cursor.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
row = cursor.fetchone()

if row is None:
    print("Пользователь не найден")
else:
    print(dict(row))

conn.close()
