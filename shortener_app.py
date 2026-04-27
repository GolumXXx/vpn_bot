import html
import json
import re
import sqlite3
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, PlainTextResponse


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "bot.db"
CODE_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

app = FastAPI()


def get_connection():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def get_link_column(conn) -> str | None:
    columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(links)").fetchall()
    }
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
            column = get_link_column(conn)
            if not column:
                return None

            row = conn.execute(
                f"SELECT {column} FROM links WHERE code = ? LIMIT 1",
                (code,),
            ).fetchone()
    except sqlite3.Error:
        return None

    if not row:
        return None

    key = row[column]
    if not key:
        return None

    return str(key).strip() or None


def render_key_page(key: str) -> str:
    escaped_key = html.escape(key, quote=True)
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
      width: min(100%, 620px);
      padding: 28px;
      border: 1px solid var(--border);
      border-radius: 8px;
      background: var(--panel);
      box-shadow: 0 24px 80px rgba(0, 0, 0, 0.35);
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
    button {{
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
    }}
    button:hover {{
      background: var(--accent-hover);
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
  <main>
    <h1 id="title">Ключ скопирован</h1>
    <p id="hint">VPN-ключ уже в буфере обмена. Если браузер запретил автокопирование, нажми кнопку ниже.</p>
    <textarea id="key" readonly spellcheck="false">{escaped_key}</textarea>
    <button id="copyButton" type="button">Скопировать ещё раз</button>
    <div id="status" class="status" aria-live="polite"></div>
  </main>
  <script>
    const key = {js_key};
    const title = document.getElementById("title");
    const statusNode = document.getElementById("status");
    const keyNode = document.getElementById("key");
    const copyButton = document.getElementById("copyButton");

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

    copyButton.addEventListener("click", copyKey);
    window.addEventListener("DOMContentLoaded", copyKey);
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

    return HTMLResponse(render_key_page(key))
