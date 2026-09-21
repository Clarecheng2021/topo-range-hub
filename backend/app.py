"""HTTP service for diagram-to-topology candidate generation."""

from __future__ import annotations

import json
import logging
import multiprocessing
import os
import re
import threading
import time
import uuid
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from backend.glm_topology import analyze


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.environ.get("APP_DATA_DIR", ROOT / "artifacts" / "jobs")).resolve()
STATIC_DIR = ROOT / "dist"
MAX_UPLOAD_BYTES = 12 * 1024 * 1024
ALLOWED_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}

app = FastAPI(title="TopoRangeHub", docs_url=None, redoc_url=None)
logger = logging.getLogger("toporangehub")
STATUS_LOCK = threading.Lock()
JOB_LOCK = threading.Lock()
JOB_PROCESSES: dict[str, multiprocessing.Process] = {}
RANGE_ENGINE_URL = os.environ.get("RANGE_ENGINE_URL", "").rstrip("/")


def range_engine_request(method: str, path: str, payload: dict | None = None) -> dict:
    """Call the internal range runtime without exposing its Docker daemon."""
    if not RANGE_ENGINE_URL:
        raise HTTPException(status_code=503, detail="虚拟靶场运行时未配置")
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(f"{RANGE_ENGINE_URL}{path}", data=body, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as error:
        try:
            message = json.loads(error.read() or b"{}").get("detail", "虚拟靶场请求失败")
        except (json.JSONDecodeError, AttributeError):
            message = "虚拟靶场请求失败"
        raise HTTPException(status_code=error.code, detail=message) from error
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        logger.warning("Range engine unavailable: %s", error)
        raise HTTPException(status_code=503, detail="虚拟靶场运行时暂不可用，请稍后重试") from error


def job_path(job_id: str) -> Path:
    if not re.fullmatch(r"[a-f0-9-]{36}", job_id):
        raise HTTPException(status_code=404, detail="Job not found")
    return DATA_DIR / job_id


def write_status(directory: Path, status: str, stage: str, progress: int, error: str | None = None) -> None:
    status_file = directory / "status.json"
    bounded_progress = max(0, min(progress, 100))
    now = datetime.now(timezone.utc).isoformat()
    # Keep status updates atomic for concurrent HTTP polling.
    with STATUS_LOCK:
        try:
            previous = json.loads(status_file.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            previous = {}
        events = [event for event in previous.get("events", [])
                  if "服务仍在等待结构化结果" not in event.get("stage", "")
                  and "暂未返回结构化片段" not in event.get("stage", "")]
        event = {"stage": stage, "progress": bounded_progress, "at": now}
        if not events or events[-1]["stage"] != stage:
            events.append(event)
        payload = {
            "status": status, "stage": stage, "progress": bounded_progress,
            "updated_at": now, "events": events[-16:],
            "created_at": previous.get("created_at") or (now if status == "queued" else None),
            "started_at": previous.get("started_at") or (now if status == "running" else None),
            "finished_at": previous.get("finished_at") or (now if status in {"completed", "failed", "cancelled"} else None),
        }
        if error:
            payload["error"] = error
        # Polling can happen while a job changes state.  Replace atomically so
        # readers never observe the transient empty file of a normal overwrite.
        temporary = directory / "status.json.tmp"
        temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        temporary.replace(status_file)


def run_analysis_worker(directory: Path, scope: str, reasoning_effort: str = "low") -> None:
    def report(stage: str, progress: int) -> None:
        write_status(directory, "running", stage, progress)
    last_output_write = 0.0
    latest_output = ""

    def save_output(content: str, force: bool = False) -> None:
        nonlocal last_output_write, latest_output
        latest_output = content
        now = time.monotonic()
        if not force and now - last_output_write < 0.3:
            return
        temporary = directory / "output.txt.tmp"
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(directory / "output.txt")
        if not last_output_write:
            report("正在接收模型识别结果", 25)
        last_output_write = now

    try:
        report("正在准备图像", 10)
        image_path = next(directory.glob("source.*"))
        topology = analyze(image_path, scope, report, save_output, reasoning_effort=reasoning_effort)
        save_output(latest_output, force=True)
        topology["source"]["job_id"] = directory.name
        (directory / "topology.json").write_text(json.dumps(topology, ensure_ascii=False, indent=2), encoding="utf-8")
        write_status(directory, "completed", "矢量拓扑已生成，等待审核", 100)
    except Exception as error:  # Preserve a user-readable result without leaking API keys.
        if latest_output:
            save_output(latest_output, force=True)
        logger.exception("Topology job %s failed", directory.name)
        write_status(directory, "failed", "识别失败", 100, str(error))


def run_analysis_job(directory: Path, scope: str, reasoning_effort: str = "low") -> None:
    # A dedicated process lets cancellation close a blocked upstream socket,
    # including the period before the provider sends its first token.
    with JOB_LOCK:
        state = json.loads((directory / "status.json").read_text(encoding="utf-8"))
        if state.get("status") == "cancelled":
            return
        process = multiprocessing.get_context("spawn").Process(
            target=run_analysis_worker, args=(directory, scope, reasoning_effort), daemon=True,
        )
        try:
            process.start()
        except Exception as error:
            logger.exception("Could not start job %s", directory.name)
            write_status(directory, "failed", "识别任务启动失败", 0, str(error))
            return
        JOB_PROCESSES[directory.name] = process

    def reap() -> None:
        process.join()
        with JOB_LOCK:
            JOB_PROCESSES.pop(directory.name, None)
            state = json.loads((directory / "status.json").read_text(encoding="utf-8"))
            if state.get("status") in {"running", "queued"}:
                write_status(directory, "failed", "识别进程异常退出", 0, "识别进程已退出，请重新识别。")
    threading.Thread(target=reap, daemon=True).start()


@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: str) -> dict[str, str]:
    directory = job_path(job_id)
    with JOB_LOCK:
        status_file = directory / "status.json"
        if not status_file.is_file():
            raise HTTPException(status_code=404, detail="Job not found")
        state = json.loads(status_file.read_text(encoding="utf-8"))
        if state.get("status") in {"completed", "failed", "cancelled"}:
            return {"status": state["status"]}
        process = JOB_PROCESSES.get(job_id)
        if process and process.is_alive():
            process.terminate()
            process.join(timeout=2)
            if process.is_alive():
                process.kill()
                process.join(timeout=2)
            if process.is_alive():
                raise HTTPException(status_code=503, detail="停止任务失败，请重试")
        # Only publish cancellation after the writer has stopped. Partial output
        # and the source image remain available for display and a fresh retry.
        write_status(directory, "cancelled", "识别已停止，原图及已收到的结果已保留", 0)
    return {"status": "cancelled"}


@app.on_event("startup")
def recover_interrupted_jobs() -> None:
    # In-process tasks cannot survive a container restart. Preserve their image
    # and partial output, but never leave an interrupted request running forever.
    for status_file in DATA_DIR.glob("*/status.json"):
        try:
            state = json.loads(status_file.read_text(encoding="utf-8"))
            if state.get("status") in {"running", "queued"}:
                write_status(status_file.parent, "failed", "识别任务因服务重启中断", 0,
                             "服务已重启，原图已保存，请点击分析按钮重新识别。")
        except (OSError, json.JSONDecodeError):
            logger.warning("Could not recover job state: %s", status_file.parent.name)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "model": os.environ.get("ZHIPU_VISION_MODEL", "glm-5.3-flash")}


@app.get("/api/ranges/health")
def range_health() -> dict:
    return range_engine_request("GET", "/health")


@app.get("/api/ranges")
def list_ranges() -> dict:
    return range_engine_request("GET", "/deployments")


@app.delete("/api/ranges/{range_id}")
def destroy_range(range_id: str) -> dict:
    return range_engine_request("DELETE", f"/deployments/{range_id}")

@app.post("/api/ranges/deploy", status_code=201)
def deploy_range(topology: dict) -> dict:
    # The engine independently rejects unsafe topology and missing approval.
    return range_engine_request("POST", "/deployments", topology)

@app.post("/api/analyze", status_code=202)
async def create_analysis(background_tasks: BackgroundTasks, image: UploadFile = File(...), scope: str = Form("生产工控网"), reasoning_effort: str = Form("low")) -> JSONResponse:
    if reasoning_effort not in {"low", "high", "max"}:
        raise HTTPException(status_code=422, detail="思考强度必须为 low、high 或 max")
    suffix = Path(image.filename or "upload").suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(status_code=415, detail="Only PNG, JPEG, and WebP images are supported.")
    content = await image.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Image exceeds the 12 MB limit.")
    job_id = str(uuid.uuid4())
    directory = job_path(job_id)
    directory.mkdir(parents=True, exist_ok=False)
    image_path = directory / f"source{suffix}"
    image_path.write_bytes(content)
    write_status(directory, "queued", "图片已上传，等待识别任务启动", 5)
    background_tasks.add_task(run_analysis_job, directory, scope.strip() or "生产工控网", reasoning_effort)
    return JSONResponse({"job_id": job_id, "status": "queued"}, status_code=202)


@app.get("/api/jobs/{job_id}")
def get_job_status(job_id: str) -> JSONResponse:
    status_file = job_path(job_id) / "status.json"
    if not status_file.is_file():
        raise HTTPException(status_code=404, detail="Job not found")
    try:
        payload = json.loads(status_file.read_text(encoding="utf-8"))
        payload["events"] = [event for event in payload.get("events", [])
                             if "服务仍在等待结构化结果" not in event.get("stage", "")
                             and "暂未返回结构化片段" not in event.get("stage", "")]
        return JSONResponse(payload)
    except json.JSONDecodeError as error:
        raise HTTPException(status_code=503, detail="任务状态正在更新，请稍后重试") from error


@app.get("/api/jobs/{job_id}/topology")
def get_topology(job_id: str) -> JSONResponse:
    output = job_path(job_id) / "topology.json"
    if not output.is_file():
        raise HTTPException(status_code=404, detail="Topology not found")
    return JSONResponse(json.loads(output.read_text(encoding="utf-8")))


@app.get("/api/jobs/{job_id}/source")
def get_source(job_id: str) -> FileResponse:
    image = next(job_path(job_id).glob("source.*"), None)
    if not image:
        raise HTTPException(status_code=404, detail="Source image not found")
    return FileResponse(image)


@app.get("/api/jobs/{job_id}/output")
def get_output(job_id: str) -> PlainTextResponse:
    directory = job_path(job_id)
    if not (directory / "status.json").is_file():
        raise HTTPException(status_code=404, detail="Job not found")
    output = directory / "output.txt"
    return PlainTextResponse(output.read_text(encoding="utf-8") if output.is_file() else "", headers={"Cache-Control": "no-store"})


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
