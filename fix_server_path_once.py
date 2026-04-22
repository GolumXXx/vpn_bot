from database.db import get_connection

conn = get_connection()
cursor = conn.cursor()

# Меняем путь у сервера с ID = 1
cursor.execute(
    """
    UPDATE servers
    SET web_base_path = ?
    WHERE id = ?
    """,
    ("/xa3kbve9IszMhaecx1", 1),
)

conn.commit()
conn.close()

print("Путь сервера обновлён ✅")