from fastapi import FastAPI
from fastapi.responses import JSONResponse, RedirectResponse

from config import DB_PATH
from services.short_links import get_vless_by_code, normalize_code

app = FastAPI()


def find_key_by_code(code: str) -> str | None:
    normalized_code = normalize_code(code)
    if not normalized_code:
        return None

    link = get_vless_by_code(normalized_code)
    return str(link).strip() if link else None


@app.get("/api/health")
def healthcheck():
    return {"status": "ok"}


@app.get("/s/{code}")
def open_short_link(code: str):
    normalized_code = normalize_code(code)
    log_code = normalized_code or str(code).strip()
    print(f"[SHORTLINK] Using DB: {DB_PATH}")

    if not normalized_code:
        print(f"[SHORTLINK] code={log_code}, found=False")
        return JSONResponse({"error": "invalid code"}, status_code=400)

    key = find_key_by_code(normalized_code)
    print(f"[SHORTLINK] code={log_code}, found={bool(key)}")
    if not key:
        return JSONResponse({"error": "Link not found"}, status_code=404)

    return RedirectResponse(url=key, status_code=307)
