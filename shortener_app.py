import html
import json

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse

from config import DB_PATH
from services.platega import PlategaAPIError, PlategaConfigError, PlategaWebhookAuthError
from services.platega_webhook import process_webhook
from services.short_links import get_vless_by_code, normalize_code

app = FastAPI()


def find_key_by_code(code: str) -> str | None:
    normalized_code = normalize_code(code)
    if not normalized_code:
        return None

    link = get_vless_by_code(normalized_code)
    return str(link).strip() if link else None


def render_key_page(vless: str) -> str:
    escaped_vless = html.escape(vless, quote=True)
    js_vless = (
        json.dumps(vless)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )

    return f"""<!doctype html>
<html lang="ru">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>VPN подключение</title>
    <style>
        body {{
            background: #0f172a;
            color: white;
            font-family: Arial, sans-serif;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            margin: 0;
            padding: 16px;
        }}
        .card {{
            background: #1e293b;
            padding: 20px;
            border-radius: 12px;
            width: 90%;
            max-width: 400px;
            text-align: center;
            box-sizing: border-box;
        }}
        textarea {{
            width: 100%;
            height: 100px;
            margin-top: 10px;
            border-radius: 8px;
            border: none;
            padding: 10px;
            background: #334155;
            color: white;
            box-sizing: border-box;
            resize: vertical;
        }}
        button {{
            margin-top: 15px;
            padding: 12px;
            width: 100%;
            border: none;
            border-radius: 8px;
            font-size: 16px;
            cursor: pointer;
        }}
        .copy {{
            background: #22c55e;
        }}
        .open {{
            background: #3b82f6;
            color: white;
        }}
    </style>
</head>
<body>
    <div class="card">
        <h2>Скопируй ключ</h2>
        <textarea id="link" readonly>{escaped_vless}</textarea>

        <button class="copy" onclick="copyKey()">Скопировать</button>
        <button class="open" onclick="openVPN()">Открыть VPN</button>
    </div>

    <script>
        const vpnLink = {js_vless};

        async function copyKey(showAlert = true) {{
            const text = document.getElementById("link");
            try {{
                await navigator.clipboard.writeText(vpnLink);
            }} catch (error) {{
                text.focus();
                text.select();
                document.execCommand("copy");
            }}

            if (showAlert) {{
                alert("Скопировано!");
            }}
        }}

        function openVPN() {{
            window.location.href = vpnLink;
        }}

        window.addEventListener("load", function() {{
            copyKey(false);
        }});
    </script>
</body>
</html>"""


@app.get("/api/health")
def healthcheck():
    return {"status": "ok"}


@app.post("/api/payment/webhook")
async def payment_webhook(request: Request):
    try:
        payload = await request.json()
    except (json.JSONDecodeError, ValueError):
        return JSONResponse({"ok": False, "error": "invalid json"}, status_code=400)

    try:
        result = await process_webhook(payload, request.headers)
    except PlategaWebhookAuthError:
        print("[PLATEGA] unauthorized webhook")
        return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
    except PlategaConfigError:
        return JSONResponse({"ok": False, "error": "platega is not configured"}, status_code=503)
    except PlategaAPIError:
        return JSONResponse({"ok": False, "error": "platega verification failed"}, status_code=502)

    return JSONResponse(result, status_code=200)


@app.get("/s/{code}", response_class=HTMLResponse)
def open_short_link(code: str):
    normalized_code = normalize_code(code)
    log_code = normalized_code or str(code).strip()
    print(f"[SHORTLINK] Using DB: {DB_PATH}")

    if not normalized_code:
        print(f"[SHORTLINK] code={log_code}, found=False")
        return HTMLResponse("<h1>invalid code</h1>", status_code=400)

    key = find_key_by_code(normalized_code)
    print(f"[SHORTLINK] code={log_code}, found={bool(key)}")
    if not key:
        return HTMLResponse("<h1>Link not found</h1>", status_code=404)

    return HTMLResponse(content=render_key_page(key))
