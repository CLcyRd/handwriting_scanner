from pathlib import Path
from typing import Dict
from app.models import TaskState

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
