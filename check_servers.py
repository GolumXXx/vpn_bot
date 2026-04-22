import sqlite3

conn = sqlite3.connect("bot.db")
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# Проверяем, есть ли вообще таблица servers
cursor.execute("""
    SELECT name
    FROM sqlite_master
    WHERE type='table' AND name='servers'
""")
table_exists = cursor.fetchone()

if not table_exists:
    print("Таблицы servers вообще нет ❌")
    conn.close()
    raise SystemExit

# Получаем все серверы
cursor.execute("SELECT * FROM servers")
rows = cursor.fetchall()

if not rows:
    print("Таблица servers есть, но серверов в ней нет ❌")
else:
    print(f"Найдено серверов: {len(rows)} ✅")
    print()

    for row in rows:
        print(f"ID: {row['id']}")
        print(f"Имя: {row['name']}")
        print(f"Host: {row['host']}")
        print(f"Port: {row['port']}")
        print(f"Protocol: {row['protocol']}")
        print(f"Path: {row['web_base_path']}")
        print(f"Login: {row['login']}")
        print(f"is_active: {row['is_active']}")
        print("-" * 30)

conn.close()