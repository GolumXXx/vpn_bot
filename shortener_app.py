from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse

from services.short_links import get_original_url

app = FastAPI()


@app.get("/api/health")
def healthcheck():
    return {"status": "ok"}


@app.get("/{code}")
def redirect_short_link(code: str):
    original_url = get_original_url(code)
    if not original_url:
        raise HTTPException(status_code=404, detail="Ссылка не найдена")
    return RedirectResponse(url=original_url)