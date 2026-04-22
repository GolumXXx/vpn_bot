from database.db import get_connection

conn = get_connection()
cursor = conn.cursor()

# Обновляем логин и пароль у основного сервера
cursor.execute(
    """
    UPDATE servers
    SET login = ?, password = ?
    WHERE id = ?
    """,
    (
        "76MGN2fVMM",     # сюда впиши реальный логин панели
        "JIx4ZaXNid",    # сюда впиши реальный пароль панели
        1
    ),
)

conn.commit()
conn.close()

print("Логин и пароль сервера обновлены ✅")