import sqlite3

conn = sqlite3.connect("bot.db")
cursor = conn.cursor()

cursor.execute("PRAGMA table_info(vpn_keys)")
columns = cursor.fetchall()

print("Колонки таблицы vpn_keys:")
for column in columns:
    print(column)

conn.close()