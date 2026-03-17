import asyncio
import json
import os
import uuid
from pathlib import Path
from typing import Dict

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from langchain_core.chat_history import InMemoryChatMessageHistory
from langchain_core.messages import AIMessage, HumanMessage

from app.models import TaskState
from app.recognizer import GeminiRecognizer
from app.file_utils import convert_pdf_to_images, build_docx

load_dotenv()


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
STATIC_DIR = BASE_DIR / "static"


TASKS: Dict[str, TaskState] = {}


def load_task_from_disk(task_id: str) -> TaskState | None:
    task_dir = DATA_DIR / task_id
    if not task_dir.exists():
        return None

    # Find PDF file
    pdf_files = list(task_dir.glob("*.pdf"))
    if not pdf_files:
        return None
    pdf_path = pdf_files[0]

    # Find images
    pages_dir = task_dir / "pages"
    image_paths = sorted(pages_dir.glob("*.png")) if pages_dir.exists() else []

    # Find docx
    docx_files = list(task_dir.glob("*_recognized.docx"))
    docx_path = docx_files[0] if docx_files else None

    # Try to load results (optional, if we save them later)
    results = {}
    
    # Determine status
    if docx_path and docx_path.exists():
        status = "completed"
    elif image_paths:
        status = "uploaded" # or processing/failed, but uploaded is safe default
    else:
        status = "failed"

    task = TaskState(
        task_id=task_id,
        filename=pdf_path.name,
        pdf_path=pdf_path,
        image_paths=image_paths,
        total_pages=len(image_paths),
        status=status,
        results=results,
        docx_path=docx_path
    )
    TASKS[task_id] = task
    return task


def get_task(task_id: str) -> TaskState | None:
    if task_id in TASKS:
        return TASKS[task_id]
    return load_task_from_disk(task_id)


def serialize_event(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


app = FastAPI(title="老电影艺术家手稿 AI 识别系统")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    return (STATIC_DIR / "index.html").read_text(encoding="utf-8")


@app.post("/api/upload")
async def upload_pdf(file: UploadFile = File(...)) -> dict:
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="仅支持 PDF 文件")
    task_id = str(uuid.uuid4())
    task_dir = DATA_DIR / task_id
    task_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = task_dir / file.filename
    pdf_path.write_bytes(await file.read())
    try:
        image_paths = await asyncio.to_thread(convert_pdf_to_images, pdf_path, task_dir / "pages")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"PDF 解析失败: {exc}") from exc
    task = TaskState(
        task_id=task_id,
        filename=file.filename,
        pdf_path=pdf_path,
        image_paths=image_paths,
        total_pages=len(image_paths),
    )
    TASKS[task_id] = task
    return {"task_id": task_id, "total_pages": task.total_pages}


@app.get("/api/recognize/{task_id}")
async def recognize(task_id: str) -> StreamingResponse:
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY environment variable not found.")
        raise HTTPException(status_code=500, detail="缺少 GEMINI_API_KEY 环境变量")

    async def event_generator():
        if task.status == "completed":
            for page, text in sorted(task.results.items()):
                yield serialize_event({"page": page, "text": text, "status": "processing"})
            yield serialize_event({"status": "completed", "download_url": f"/api/download/{task_id}"})
            return
        
        # If task is already processing, tell client to wait or just return
        if task.status == "processing":
             # In a real system we might want to attach to the existing stream or similar,
             # but here we just notify.
            yield serialize_event({"status": "processing", "message": "任务正在处理中"})
            return

        task.status = "processing"
        recognizer = GeminiRecognizer(api_key=api_key)
        chat_history = InMemoryChatMessageHistory()
        
        # Rebuild history from existing results if any
        for idx in sorted(task.results.keys()):
            text = task.results[idx]
            chat_history.add_messages([HumanMessage(content=f"第{idx}页"), AIMessage(content=text)])

        try:
            for index, image_path in enumerate(task.image_paths, start=1):
                # Check for pause signal
                if task.status == "paused":
                    yield serialize_event({"status": "paused", "message": "任务已暂停"})
                    return

                # Skip if already recognized
                if index in task.results:
                    yield serialize_event({"page": index, "text": task.results[index], "status": "processing"})
                    continue

                history = "\n".join(
                    message.content for message in chat_history.messages if isinstance(message, AIMessage)
                )
                text = await asyncio.to_thread(
                    recognizer.recognize_page,
                    image_path,
                    history,
                    index,
                    task.total_pages,
                )
                task.results[index] = text
                chat_history.add_messages([HumanMessage(content=f"第{index}页"), AIMessage(content=text)])
                yield serialize_event({"page": index, "text": text, "status": "processing"})
            
            # Check pause again before finalizing
            if task.status == "paused":
                 yield serialize_event({"status": "paused", "message": "任务已暂停"})
                 return

            task.docx_path = await asyncio.to_thread(build_docx, task)
            task.status = "completed"
            yield serialize_event({"status": "completed", "download_url": f"/api/download/{task_id}"})
        except Exception as exc:
            task.status = "failed"
            task.error = str(exc)
            yield serialize_event({"status": "failed", "message": task.error})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@app.post("/api/pause/{task_id}")
async def pause_task(task_id: str) -> dict:
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task.status == "processing":
        task.status = "paused"
    return {"status": task.status}


@app.post("/api/restart/{task_id}")
async def restart_task(task_id: str) -> dict:
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    # Reset task state
    task.status = "uploaded"
    task.results = {}
    task.docx_path = None
    task.error = None
    
    # Optional: Delete existing docx file if it exists
    # docx_path = ... (we don't strictly need to delete it from disk immediately, it will be overwritten)
    
    return {"status": "restarted"}


@app.get("/api/download/{task_id}")
async def download_docx(task_id: str) -> FileResponse:
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task.status != "completed" or not task.docx_path or not task.docx_path.exists():
        raise HTTPException(status_code=400, detail="文档尚未生成")
    return FileResponse(
        path=task.docx_path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=task.docx_path.name,
    )
