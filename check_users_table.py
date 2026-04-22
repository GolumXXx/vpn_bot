import sqlite3

conn = sqlite3.connect("bot.db")
cursor = conn.cursor()

cursor.execute("PRAGMA table_info(users)")
columns = cursor.fetchall()

print("Колонки таблицы users:")
for column in columns:
    print(column)

conn.close()