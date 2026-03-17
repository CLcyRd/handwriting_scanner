from pathlib import Path
from typing import Dict

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.models import TaskState
from app.routes import router
from app.shared import STATIC_DIR

load_dotenv()


app = FastAPI(title="老电影艺术家手稿 AI 识别系统")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.include_router(router, prefix="/api")


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    return (STATIC_DIR / "index.html").read_text(encoding="utf-8")
