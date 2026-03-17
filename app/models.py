from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List


@dataclass
class TaskState:
    task_id: str
    filename: str
    pdf_path: Path
    image_paths: List[Path]
    total_pages: int
    status: str = "uploaded"
    results: Dict[int, str] = field(default_factory=dict)
    docx_path: Path | None = None
    error: str | None = None
