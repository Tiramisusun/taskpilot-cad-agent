from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv
from pydantic import BaseModel
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .cad_parser import read_dxf
from .models import DrawingModel, NormDocument
from .norms import load_norm, search_norms
from .repair import apply_low_risk_fixes
from .report import write_html_report, write_json_report
from .reviewer import review_drawing
from .taskpilot.memory import MemoryStore
from .taskpilot.middleware import MiddlewareStack
from .taskpilot.observability import EventLog
from .taskpilot.deepagent_runtime import DeepAgentRuntime
from .taskpilot.runtime import AgentRuntime


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
REPORT_DIR = DATA_DIR / "reports"
LOG_DIR = DATA_DIR / "events"
MEMORY_PATH = DATA_DIR / "memory" / "memory.json"
STATIC_DIR = BASE_DIR / "static"

for directory in (UPLOAD_DIR, REPORT_DIR):
    directory.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="CAD AI Review Agent", version="0.1.0")

DRAWINGS: dict[str, tuple[Path, DrawingModel]] = {}
NORMS: dict[str, NormDocument] = {}
REVIEWS: dict[str, dict] = {}

EVENT_LOG = EventLog(LOG_DIR)
MEMORY = MemoryStore.load(MEMORY_PATH)
MIDDLEWARE = MiddlewareStack(EVENT_LOG, MEMORY)
RUNTIME = AgentRuntime(DRAWINGS, NORMS, REPORT_DIR, EVENT_LOG, MIDDLEWARE)
DEEP_RUNTIME = DeepAgentRuntime(RUNTIME)


class ReviewRequest(BaseModel):
    drawing_id: str
    norm_query: str = ""


class TaskRequest(BaseModel):
    objective: str = "Review the CAD drawing against uploaded standards and generate a repaired DXF with review reports."
    drawing_id: str
    norm_query: str = ""


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "service": "cad-ai-review-agent"}


@app.get("/api/tools")
def list_tools() -> dict:
    return {"tools": RUNTIME.registry.list_tools()}


@app.post("/api/drawings")
async def upload_drawing(request: Request, x_filename: str = Header(default="drawing.dxf")) -> dict:
    if not x_filename.lower().endswith(".dxf"):
        raise HTTPException(status_code=400, detail="Please upload a .dxf file. Convert DWG to DXF before uploading.")
    drawing_id = uuid4().hex
    path = UPLOAD_DIR / f"{drawing_id}_{Path(x_filename).name}"
    path.write_bytes(await request.body())
    drawing = read_dxf(path)
    DRAWINGS[drawing_id] = (path, drawing)
    return {"drawing_id": drawing_id, "summary": drawing.to_summary()}


@app.post("/api/norms")
async def upload_norm(request: Request, x_filename: str = Header(default="norm.txt")) -> dict:
    if not x_filename:
        raise HTTPException(status_code=400, detail="Missing filename.")
    norm_id = uuid4().hex
    path = UPLOAD_DIR / f"{norm_id}_{Path(x_filename).name}"
    path.write_bytes(await request.body())
    norm = load_norm(path)
    NORMS[norm_id] = norm
    return {"norm_id": norm_id, "filename": norm.filename, "chunks": len(norm.chunks)}


@app.get("/api/norms/search")
def search_norms_endpoint(q: str) -> dict:
    return {"matches": search_norms(list(NORMS.values()), q)}


@app.post("/api/reviews")
def create_review(payload: ReviewRequest) -> dict:
    if payload.drawing_id not in DRAWINGS:
        raise HTTPException(status_code=404, detail="Drawing not found. Please upload it again.")
    source_path, drawing = DRAWINGS[payload.drawing_id]
    norm_matches = search_norms(list(NORMS.values()), payload.norm_query or "architectural drawing review")
    issues = review_drawing(drawing, list(NORMS.values()), payload.norm_query)
    review_id = uuid4().hex
    json_path = REPORT_DIR / f"{review_id}.json"
    html_path = REPORT_DIR / f"{review_id}.html"
    fixed_path = REPORT_DIR / f"{review_id}_fixed.dxf"

    write_json_report(json_path, drawing, issues, norm_matches)
    write_html_report(html_path, drawing, issues, norm_matches)
    repair_result = apply_low_risk_fixes(source_path, fixed_path, issues)

    REVIEWS[review_id] = {
        "drawing_id": payload.drawing_id,
        "json_path": json_path,
        "html_path": html_path,
        "fixed_path": fixed_path,
        "issues": issues,
        "repair_result": repair_result,
    }
    return {
        "review_id": review_id,
        "drawing": drawing.to_summary(),
        "issues": [issue.to_dict() for issue in issues],
        "norm_matches": norm_matches,
        "downloads": {
            "json": f"/api/reviews/{review_id}/report.json",
            "html": f"/api/reviews/{review_id}/report.html",
            "fixed_dxf": f"/api/reviews/{review_id}/fixed.dxf",
        },
        "repair_result": repair_result,
    }


@app.post("/api/tasks")
async def create_task(payload: TaskRequest) -> dict:
    if payload.drawing_id not in DRAWINGS:
        raise HTTPException(status_code=404, detail="Drawing not found. Please upload it again.")
    task = RUNTIME.create_task(payload.objective, payload.drawing_id, payload.norm_query)
    await RUNTIME.run_task(task.task_id)
    result = task.to_dict()
    _register_task_review_downloads(result)
    return result


@app.post("/api/tasks/deepagent")
async def create_deepagent_task(payload: TaskRequest) -> dict:
    if payload.drawing_id not in DRAWINGS:
        raise HTTPException(status_code=404, detail="Drawing not found. Please upload it again.")
    task = RUNTIME.create_task(payload.objective, payload.drawing_id, payload.norm_query)
    await DEEP_RUNTIME.run_task(task.task_id)
    result = task.to_dict()
    _register_task_review_downloads(result)
    return result


@app.post("/api/tasks/async")
async def create_task_async(payload: TaskRequest) -> dict:
    if payload.drawing_id not in DRAWINGS:
        raise HTTPException(status_code=404, detail="Drawing not found. Please upload it again.")
    task = RUNTIME.create_task(payload.objective, payload.drawing_id, payload.norm_query)
    import asyncio

    asyncio.create_task(RUNTIME.run_task(task.task_id))
    return task.to_dict()


@app.get("/api/tasks")
def list_tasks() -> dict:
    return {"tasks": [task.to_dict() for task in RUNTIME.tasks.list()]}


@app.get("/api/tasks/{task_id}")
def get_task(task_id: str) -> dict:
    task = RUNTIME.tasks.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found.")
    result = task.to_dict()
    _register_task_review_downloads(result)
    return result


@app.get("/api/tasks/{task_id}/events")
async def stream_task_events(task_id: str) -> StreamingResponse:
    if RUNTIME.tasks.get(task_id) is None:
        raise HTTPException(status_code=404, detail="Task not found.")
    return StreamingResponse(RUNTIME.event_stream(task_id), media_type="text/event-stream")


@app.get("/api/tasks/{task_id}/replay")
def replay_task(task_id: str) -> dict:
    if RUNTIME.tasks.get(task_id) is None:
        raise HTTPException(status_code=404, detail="Task not found.")
    return {"events": EVENT_LOG.replay(task_id)}


@app.get("/api/reviews/{review_id}/report.json")
def download_json(review_id: str) -> FileResponse:
    return _download(review_id, "json_path", "application/json")


@app.get("/api/reviews/{review_id}/report.html")
def download_html(review_id: str) -> FileResponse:
    return _download(review_id, "html_path", "text/html")


@app.get("/api/reviews/{review_id}/fixed.dxf")
def download_fixed_dxf(review_id: str) -> FileResponse:
    return _download(review_id, "fixed_path", "application/dxf")


def _download(review_id: str, key: str, media_type: str) -> FileResponse:
    if review_id not in REVIEWS:
        candidate = _report_candidate(review_id, key)
        if candidate.exists():
            return FileResponse(candidate, media_type=media_type, filename=candidate.name)
        raise HTTPException(status_code=404, detail="Review record not found.")
    path = REVIEWS[review_id][key]
    return FileResponse(path, media_type=media_type, filename=path.name)


def _report_candidate(review_id: str, key: str) -> Path:
    if key == "json_path":
        return REPORT_DIR / f"{review_id}.json"
    if key == "html_path":
        return REPORT_DIR / f"{review_id}.html"
    return REPORT_DIR / f"{review_id}_fixed.dxf"


def _register_task_review_downloads(task_payload: dict) -> None:
    result = task_payload.get("result") or {}
    review_id = result.get("review_id")
    if not review_id or review_id in REVIEWS:
        return
    REVIEWS[review_id] = {
        "drawing_id": task_payload.get("drawing_id"),
        "json_path": REPORT_DIR / f"{review_id}.json",
        "html_path": REPORT_DIR / f"{review_id}.html",
        "fixed_path": REPORT_DIR / f"{review_id}_fixed.dxf",
        "issues": result.get("issues", []),
        "repair_result": result.get("repair_result", {}),
    }


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
