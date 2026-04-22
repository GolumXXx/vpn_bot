from database.db import init_db, add_server

init_db()

add_server(
    name="MyVpn",
    host="144.31.65.15",
    port=21629,
    protocol="https",
    web_base_path="/xa3kbve9IszMhaecx1",
    login="76MGN2fVMM",
    password="JIx4ZaXNid",
)

print("Сервер добавлен в базу ✅")