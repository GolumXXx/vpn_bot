import asyncio
import sqlite3
from database.db import delete_key_completely

conn = sqlite3.connect("bot.db")
cursor = conn.cursor()

cursor.execute("SELECT id, key_name, panel_email FROM vpn_keys ORDER BY id DESC LIMIT 10")
rows = cursor.fetchall()

print("Последние ключи:")
for row in rows:
    print(row)

conn.close()


async def main():
    key_id = int(input("Введи ID ключа для удаления: "))
    success, message = await delete_key_completely(key_id)
    print(success, message)

asyncio.run(main())