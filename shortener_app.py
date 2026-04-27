import html
import json
import re
import sqlite3
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, PlainTextResponse

from config import SHORTENER_PUBLIC_BASE_URL


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "bot.db"
CODE_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
PUBLIC_BASE_URL = SHORTENER_PUBLIC_BASE_URL

app = FastAPI()


def get_connection():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def get_link_select_expression(conn) -> str | None:
    columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(links)").fetchall()
    }
    if "url" in columns and "vless" in columns:
        return "COALESCE(url, vless)"
    if "url" in columns:
        return "url"
    if "vless" in columns:
        return "vless"
    return None


def find_key_by_code(code: str) -> str | None:
    if not code or not CODE_RE.fullmatch(code):
        return None

    try:
        with get_connection() as conn:
            value_expression = get_link_select_expression(conn)
            if not value_expression:
                return None

            row = conn.execute(
                f"SELECT {value_expression} AS url FROM links WHERE code = ? LIMIT 1",
                (code,),
            ).fetchone()
    except sqlite3.Error:
        return None

    if not row:
        return None

    key = row["url"]
    if not key:
        return None

    return str(key).strip() or None


def render_key_page(key: str, code: str) -> str:
    escaped_key = html.escape(key, quote=True)
    browser_url = f"{PUBLIC_BASE_URL}/s/{code}" if PUBLIC_BASE_URL else f"/s/{code}"
    escaped_browser_url = html.escape(browser_url, quote=True)
    js_key = (
        json.dumps(key)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )

    return f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>VPN key</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #0b0f19;
      --panel: #111827;
      --panel-soft: #172033;
      --text: #f8fafc;
      --muted: #94a3b8;
      --accent: #22c55e;
      --accent-hover: #16a34a;
      --border: #263244;
    }}
    * {{
      box-sizing: border-box;
    }}
    body {{
      margin: 0;
      min-height: 100vh;
      display: grid;
      place-items: center;
      padding: 24px;
      background: var(--bg);
      color: var(--text);
      font-family: Inter, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    main {{
      display: block;
      width: min(100%, 620px);
      padding: 28px;
      border: 1px solid var(--border);
      border-radius: 8px;
      background: var(--panel);
      box-shadow: 0 24px 80px rgba(0, 0, 0, 0.35);
    }}
    main.is-visible {{
      display: block;
    }}
    h1 {{
      margin: 0 0 8px;
      font-size: 28px;
      line-height: 1.15;
      font-weight: 750;
      letter-spacing: 0;
    }}
    p {{
      margin: 0 0 18px;
      color: var(--muted);
      line-height: 1.5;
    }}
    textarea {{
      width: 100%;
      min-height: 150px;
      resize: vertical;
      padding: 14px;
      border: 1px solid var(--border);
      border-radius: 8px;
      outline: none;
      background: var(--panel-soft);
      color: var(--text);
      font: 13px/1.45 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    }}
    textarea:focus {{
      border-color: var(--accent);
    }}
    button,
    .button-link {{
      display: block;
      width: 100%;
      margin-top: 16px;
      padding: 13px 16px;
      border: 0;
      border-radius: 8px;
      background: var(--accent);
      color: #04130a;
      font: inherit;
      font-weight: 700;
      cursor: pointer;
      text-align: center;
      text-decoration: none;
    }}
    button:hover,
    .button-link:hover {{
      background: var(--accent-hover);
    }}
    .secondary {{
      background: transparent;
      color: var(--text);
      border: 1px solid var(--border);
    }}
    .secondary:hover {{
      background: var(--panel-soft);
    }}
    .status {{
      margin-top: 12px;
      min-height: 22px;
      color: var(--muted);
      font-size: 14px;
    }}
  </style>
</head>
<body>
  <main id="fallback">
    <h1 id="title">Подключить VPN</h1>
    <p id="hint">Нажми кнопку, чтобы открыть ключ в VPN-приложении.</p>
    <button id="openVpn" type="button">🚀 Открыть VPN</button>
    <p>Если VPN не открылся — нажмите кнопку выше.</p>
    <a class="button-link secondary" href="{escaped_browser_url}" target="_blank" rel="noopener noreferrer">🌐 Открыть в браузере</a>
    <textarea id="key" readonly spellcheck="false">{escaped_key}</textarea>
    <button id="copyButton" class="secondary" type="button">Скопировать</button>
    <div id="status" class="status" aria-live="polite"></div>
  </main>
  <script>
    const key = {js_key};
    const title = document.getElementById("title");
    const statusNode = document.getElementById("status");
    const keyNode = document.getElementById("key");
    const openVpnButton = document.getElementById("openVpn");
    const copyButton = document.getElementById("copyButton");

    function openVpn() {{
      if (!key) {{
        title.textContent = "Ключ не найден";
        statusNode.textContent = "Пустой ключ нельзя открыть.";
        return false;
      }}

      window.location.href = key;
      return true;
    }}

    async function copyKey() {{
      if (!key) {{
        title.textContent = "Ключ не найден";
        statusNode.textContent = "Пустой ключ нельзя скопировать.";
        return false;
      }}

      try {{
        await navigator.clipboard.writeText(key);
        title.textContent = "Ключ скопирован";
        statusNode.textContent = "Готово.";
        return true;
      }} catch (error) {{
        keyNode.focus();
        keyNode.select();
        title.textContent = "Скопируй ключ вручную";
        statusNode.textContent = "Браузер запретил автокопирование.";
        return false;
      }}
    }}

    openVpnButton.addEventListener("click", openVpn);
    copyButton.addEventListener("click", copyKey);
  </script>
</body>
</html>"""


@app.get("/api/health")
def healthcheck():
    return {"status": "ok"}


@app.get("/s/{code}", response_class=HTMLResponse)
def open_short_link(code: str):
    key = find_key_by_code(code.strip())
    if not key:
        return PlainTextResponse("Link not found", status_code=404)

    return HTMLResponse(render_key_page(key, code.strip()))
