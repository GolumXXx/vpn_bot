from database.db import get_active_server

server = get_active_server()

if server is None:
    print("get_active_server() вернул None ❌")
else:
    print("get_active_server() нашёл сервер ✅")
    print(dict(server))