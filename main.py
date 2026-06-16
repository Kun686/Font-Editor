from __future__ import annotations

from contextlib import asynccontextmanager
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
import ipaddress
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from threading import Lock
import time
from urllib.parse import quote
from uuid import uuid4

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from font_processor import FontConversionError, replacement_characters


BASE_DIR = Path(__file__).resolve().parent
MAX_UPLOAD_BYTES = 50 * 1024 * 1024
JOB_TTL_SECONDS = 6 * 60 * 60
JOB_WORKERS = 1
RECENT_CONVERSION_LIMIT = 5
RUNTIME_DIR = BASE_DIR / "runtime"
JOBS_DIR = RUNTIME_DIR / "jobs"
RECENT_CONVERSION_FILE = RUNTIME_DIR / "recent-conversion.json"
STATIC_VERSION = "20260616-2248"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    _restore_incomplete_jobs()
    yield


app = FastAPI(title="TTF 字体转换工具", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


@dataclass
class ConversionJob:
    job_id: str
    status: str
    progress: int
    message: str
    download_name: str
    output_path: Path
    created_at: float
    updated_at: float
    target_path: Path | None = None
    source_path: Path | None = None
    client_region: str = ""
    started_at: float | None = None
    completed_at: float | None = None
    duration_seconds: float | None = None
    options: dict[str, object] = field(default_factory=dict)
    error: str = ""


job_executor = ThreadPoolExecutor(max_workers=JOB_WORKERS)
jobs_lock = Lock()
jobs: dict[str, ConversionJob] = {}


def _restore_incomplete_jobs() -> None:
    _ensure_runtime_dirs()
    for job in _load_all_disk_jobs():
        if job.status in {"queued", "running"}:
            if not job.target_path or not job.target_path.exists():
                job.status = "failed"
                job.progress = 0
                job.message = "服务器重启后上传文件已丢失，请重新转换"
                job.error = job.message
                job.updated_at = time.time()
                _save_job(job)
                continue
            job.status = "queued"
            job.progress = 5
            job.message = "服务器恢复后重新排队转换"
            job.updated_at = time.time()
            with jobs_lock:
                jobs[job.job_id] = job
            _save_job(job)
            job_executor.submit(
                _run_conversion_job,
                job.job_id,
                job.target_path,
                job.source_path,
                job.output_path,
                job.options,
            )


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    html = (BASE_DIR / "templates" / "index.html").read_text(encoding="utf-8")
    html = html.replace("__STATIC_VERSION__", STATIC_VERSION)
    return HTMLResponse(html)


@app.get("/api/status")
def get_status() -> dict[str, object]:
    _cleanup_old_jobs()
    active_jobs = _active_jobs_snapshot()
    running_jobs = sum(1 for job in active_jobs if job.status == "running")
    queued_jobs = sum(1 for job in active_jobs if job.status == "queued")
    active_count = len(active_jobs)
    recent_conversions = _recent_conversions_payload()
    return {
        "active_jobs": active_count,
        "running_jobs": running_jobs,
        "queued_jobs": queued_jobs,
        "queue_message": _queue_message(active_count, running_jobs, queued_jobs),
        "recent_conversion": recent_conversions[0] if recent_conversions else None,
        "recent_conversions": recent_conversions,
    }


@app.post("/api/convert")
async def convert_font(
    background_tasks: BackgroundTasks,
    font_file: UploadFile = File(...),
    source_font_file: UploadFile | None = File(None),
    scale_percent: int = Form(100),
    weight_mode: str = Form("none"),
    effect_units: float | None = Form(None),
    effect_x_units: float | None = Form(None),
    effect_y_units: float | None = Form(None),
    effect_x_percent: float | None = Form(None),
    effect_y_percent: float | None = Form(None),
    spacing_left_percent: float = Form(0),
    spacing_right_percent: float = Form(0),
    spacing_top_percent: float = Form(0),
    spacing_bottom_percent: float = Form(0),
    replacement_scope: str = Form("digits"),
    custom_replacement_chars: str = Form(""),
) -> Response:
    filename = font_file.filename or ""
    if not filename.lower().endswith(".ttf"):
        raise HTTPException(status_code=400, detail="只支持 .ttf 字体文件")
    replacement_enabled = bool(source_font_file and (source_font_file.filename or ""))
    if replacement_enabled and not (source_font_file.filename or "").lower().endswith(".ttf"):
        raise HTTPException(status_code=400, detail="来源字体只支持 .ttf 字体文件")

    effect_x, effect_y = _resolve_effect_form_values(
        effect_units,
        effect_x_units,
        effect_y_units,
        effect_x_percent,
        effect_y_percent,
    )
    try:
        replacement_chars = (
            replacement_characters(replacement_scope, custom_replacement_chars)
            if replacement_enabled
            else ""
        )
    except FontConversionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    download_name = _download_name(
        filename,
        scale_percent=scale_percent,
        weight_mode=weight_mode,
        effect_x_units=effect_x,
        effect_y_units=effect_y,
        spacing_left_percent=spacing_left_percent,
        spacing_right_percent=spacing_right_percent,
        spacing_top_percent=spacing_top_percent,
        spacing_bottom_percent=spacing_bottom_percent,
        replacement_scope=replacement_scope if replacement_enabled else "",
    )

    target_path: Path | None = None
    source_path: Path | None = None
    output_path = _temporary_ttf_path()
    try:
        target_path, target_size = await _write_upload_to_temp(font_file, "字体文件不能超过 50MB")
        if target_size == 0:
            raise HTTPException(status_code=400, detail="字体文件为空")
        if replacement_enabled and source_font_file:
            source_path, source_size = await _write_upload_to_temp(source_font_file, "来源字体文件不能超过 50MB")
            if source_size == 0:
                raise HTTPException(status_code=400, detail="来源字体文件为空")
        _run_worker_subprocess(
            target_path,
            source_path,
            output_path,
            {
                "scale_percent": scale_percent,
                "weight_mode": weight_mode,
                "effect_units": effect_units,
                "effect_x_units": effect_x,
                "effect_y_units": effect_y,
                "spacing_left_percent": spacing_left_percent,
                "spacing_right_percent": spacing_right_percent,
                "spacing_top_percent": spacing_top_percent,
                "spacing_bottom_percent": spacing_bottom_percent,
                "replacement_chars": replacement_chars,
            },
        )
    except (FontConversionError, WorkerConversionError) as exc:
        _remove_file(output_path)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        _remove_file(output_path)
        raise
    except Exception:
        _remove_file(output_path)
        raise
    finally:
        _remove_optional_file(target_path)
        _remove_optional_file(source_path)

    background_tasks.add_task(_remove_file, output_path)
    return FileResponse(
        path=output_path,
        media_type="font/ttf",
        headers={
            "Content-Disposition": (
                "attachment; filename=converted.ttf; "
                f"filename*=UTF-8''{quote(download_name)}"
            ),
            "Cache-Control": "no-store",
        },
    )


@app.post("/api/convert-jobs")
async def create_conversion_job(
    request: Request,
    font_file: UploadFile = File(...),
    source_font_file: UploadFile | None = File(None),
    scale_percent: int = Form(100),
    weight_mode: str = Form("none"),
    effect_units: float | None = Form(None),
    effect_x_units: float | None = Form(None),
    effect_y_units: float | None = Form(None),
    effect_x_percent: float | None = Form(None),
    effect_y_percent: float | None = Form(None),
    spacing_left_percent: float = Form(0),
    spacing_right_percent: float = Form(0),
    spacing_top_percent: float = Form(0),
    spacing_bottom_percent: float = Form(0),
    replacement_scope: str = Form("digits"),
    custom_replacement_chars: str = Form(""),
) -> JSONResponse:
    _cleanup_old_jobs()
    filename = font_file.filename or ""
    if not filename.lower().endswith(".ttf"):
        raise HTTPException(status_code=400, detail="只支持 .ttf 字体文件")
    replacement_enabled = bool(source_font_file and (source_font_file.filename or ""))
    if replacement_enabled and not (source_font_file.filename or "").lower().endswith(".ttf"):
        raise HTTPException(status_code=400, detail="来源字体只支持 .ttf 字体文件")

    target_path: Path | None = None
    source_path: Path | None = None
    output_path: Path | None = None
    try:
        target_path, target_size = await _write_upload_to_temp(font_file, "字体文件不能超过 50MB")
        if target_size == 0:
            raise HTTPException(status_code=400, detail="字体文件为空")

        if replacement_enabled and source_font_file:
            source_path, source_size = await _write_upload_to_temp(source_font_file, "来源字体文件不能超过 50MB")
            if source_size == 0:
                raise HTTPException(status_code=400, detail="来源字体文件为空")

        effect_x, effect_y = _resolve_effect_form_values(
            effect_units,
            effect_x_units,
            effect_y_units,
            effect_x_percent,
            effect_y_percent,
        )
        replacement_chars = (
            replacement_characters(replacement_scope, custom_replacement_chars)
            if replacement_enabled
            else ""
        )
        download_name = _download_name(
            filename,
            scale_percent=scale_percent,
            weight_mode=weight_mode,
            effect_x_units=effect_x,
            effect_y_units=effect_y,
            spacing_left_percent=spacing_left_percent,
            spacing_right_percent=spacing_right_percent,
            spacing_top_percent=spacing_top_percent,
            spacing_bottom_percent=spacing_bottom_percent,
            replacement_scope=replacement_scope if replacement_enabled else "",
        )

        output_path = _temporary_ttf_path()
        job_id = uuid4().hex
        now = time.time()
        options = {
            "scale_percent": scale_percent,
            "weight_mode": weight_mode,
            "effect_units": effect_units,
            "effect_x_units": effect_x,
            "effect_y_units": effect_y,
            "spacing_left_percent": spacing_left_percent,
            "spacing_right_percent": spacing_right_percent,
            "spacing_top_percent": spacing_top_percent,
            "spacing_bottom_percent": spacing_bottom_percent,
            "replacement_chars": replacement_chars,
        }
        job = ConversionJob(
            job_id=job_id,
            status="queued",
            progress=5,
            message="已提交后台转换，等待处理",
            download_name=download_name,
            output_path=output_path,
            created_at=now,
            updated_at=now,
            target_path=target_path,
            source_path=source_path,
            client_region=_client_region(request),
            options=options,
        )
        with jobs_lock:
            jobs[job_id] = job
        _save_job(job)

        try:
            job_executor.submit(
                _run_conversion_job,
                job_id,
                target_path,
                source_path,
                output_path,
                options,
            )
        except Exception:
            with jobs_lock:
                jobs.pop(job_id, None)
            _remove_job_file(job_id)
            raise
        return JSONResponse(status_code=202, content=_job_payload(job))
    except FontConversionError as exc:
        _remove_optional_file(target_path)
        _remove_optional_file(source_path)
        _remove_optional_file(output_path)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        _remove_optional_file(target_path)
        _remove_optional_file(source_path)
        _remove_optional_file(output_path)
        raise
    except Exception:
        _remove_optional_file(target_path)
        _remove_optional_file(source_path)
        _remove_optional_file(output_path)
        raise


@app.get("/api/convert-jobs/{job_id}")
def get_conversion_job(job_id: str) -> dict[str, object]:
    _cleanup_old_jobs()
    job = _get_job_or_404(job_id)
    return _job_payload(job)


@app.get("/api/convert-jobs/{job_id}/download")
def download_conversion_job(job_id: str) -> FileResponse:
    _cleanup_old_jobs()
    job = _get_job_or_404(job_id)
    if job.status != "complete":
        raise HTTPException(status_code=409, detail="转换尚未完成")
    if not job.output_path.exists():
        raise HTTPException(status_code=410, detail="转换文件已过期，请重新转换")

    return FileResponse(
        path=job.output_path,
        media_type="font/ttf",
        headers={
            "Content-Disposition": (
                "attachment; filename=converted.ttf; "
                f"filename*=UTF-8''{quote(job.download_name)}"
            ),
            "Cache-Control": "no-store",
        },
    )


async def _write_upload_to_temp(upload: UploadFile, too_large_message: str) -> tuple[Path, int]:
    path = _temporary_ttf_path()
    size = 0
    try:
        with path.open("wb") as output:
            while True:
                chunk = await upload.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail=too_large_message)
                output.write(chunk)
        return path, size
    except Exception:
        _remove_file(path)
        raise
    finally:
        await upload.close()


def _run_conversion_job(
    job_id: str,
    target_path: Path,
    source_path: Path | None,
    output_path: Path,
    options: dict[str, object],
) -> None:
    started_at = time.time()
    _update_job(
        job_id,
        status="running",
        progress=10,
        message="正在转换字体，请保持页面打开",
        started_at=started_at,
    )
    try:
        _run_worker_subprocess(target_path, source_path, output_path, options)
        completed_at = time.time()
        duration_seconds = completed_at - started_at
        _update_job(
            job_id,
            status="complete",
            progress=100,
            message="转换完成",
            completed_at=completed_at,
            duration_seconds=duration_seconds,
        )
        job = _get_job_from_memory_or_disk(job_id)
        if job:
            _record_recent_conversion(job)
    except FontConversionError as exc:
        _remove_file(output_path)
        _update_job(job_id, status="failed", progress=0, message="转换失败", error=str(exc))
    except WorkerConversionError as exc:
        _remove_file(output_path)
        _update_job(job_id, status="failed", progress=0, message="转换失败", error=str(exc))
    except Exception as exc:
        _remove_file(output_path)
        _update_job(
            job_id,
            status="failed",
            progress=0,
            message="转换失败",
            error=str(exc) or "服务器转换失败，请查看后台日志",
        )
    finally:
        _remove_file(target_path)
        if source_path:
            _remove_file(source_path)


class WorkerConversionError(RuntimeError):
    pass


def _run_worker_subprocess(
    target_path: Path,
    source_path: Path | None,
    output_path: Path,
    options: dict[str, object],
) -> None:
    worker_script = BASE_DIR / "conversion_worker.py"
    command = [
        sys.executable,
        str(worker_script),
        str(target_path),
        str(source_path) if source_path else "",
        str(output_path),
        json.dumps(options, ensure_ascii=False),
    ]
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    result = subprocess.run(
        command,
        cwd=BASE_DIR,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    if result.returncode == 0:
        return

    message = (result.stderr or result.stdout or "").strip()
    if not message:
        message = f"转换进程异常退出，退出码 {result.returncode}"
    if result.returncode < 0:
        message = f"转换进程被系统终止，退出码 {result.returncode}"
    raise WorkerConversionError(message)


def _update_job(
    job_id: str,
    *,
    status: str,
    progress: int,
    message: str,
    error: str = "",
    started_at: float | None = None,
    completed_at: float | None = None,
    duration_seconds: float | None = None,
) -> None:
    with jobs_lock:
        job = jobs.get(job_id)
        if not job:
            job = _load_job_from_disk(job_id)
            if not job:
                return
            jobs[job_id] = job
        job.status = status
        job.progress = progress
        job.message = message
        job.error = error
        if started_at is not None:
            job.started_at = started_at
        if completed_at is not None:
            job.completed_at = completed_at
        if duration_seconds is not None:
            job.duration_seconds = duration_seconds
        job.updated_at = time.time()
        _save_job_unlocked(job)


def _get_job_or_404(job_id: str) -> ConversionJob:
    job = _get_job_from_memory_or_disk(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="转换任务不存在或已过期")
    return job


def _get_job_from_memory_or_disk(job_id: str) -> ConversionJob | None:
    with jobs_lock:
        job = jobs.get(job_id)
        if job:
            return job
        job = _load_job_from_disk(job_id)
        if job:
            jobs[job_id] = job
        return job


def _job_payload(job: ConversionJob) -> dict[str, object]:
    queue_position = _job_queue_position(job)
    recent_conversions = _recent_conversions_payload()
    recent_conversion = recent_conversions[0] if recent_conversions else None
    if recent_conversion is None and job.status == "complete" and job.duration_seconds is not None:
        recent_conversion = _recent_conversion_from_job(job)
        recent_conversions = [recent_conversion]
    payload: dict[str, object] = {
        "job_id": job.job_id,
        "status": job.status,
        "progress": job.progress,
        "message": job.message,
        "download_name": job.download_name,
        "queue_position": queue_position,
        "queued_ahead": max(0, queue_position - 1) if queue_position else 0,
        "recent_conversion": recent_conversion,
        "recent_conversions": recent_conversions,
    }
    if job.error:
        payload["error"] = job.error
    if job.duration_seconds is not None:
        payload["duration_seconds"] = round(job.duration_seconds, 1)
    if job.status == "complete":
        payload["download_url"] = f"/api/convert-jobs/{job.job_id}/download"
    return payload


def _job_queue_position(job: ConversionJob) -> int:
    if job.status not in {"queued", "running"}:
        return 0

    with jobs_lock:
        active_jobs = [
            active
            for active in jobs.values()
            if active.status in {"queued", "running"}
        ]

    active_jobs.sort(key=lambda active: (active.created_at, active.job_id))
    for index, active in enumerate(active_jobs, start=1):
        if active.job_id == job.job_id:
            return index
    return 0


def _active_jobs_snapshot() -> list[ConversionJob]:
    with jobs_lock:
        active_by_id = {
            job.job_id: job
            for job in jobs.values()
            if job.status in {"queued", "running"}
        }

    for job in _load_all_disk_jobs():
        if job.status in {"queued", "running"}:
            active_by_id.setdefault(job.job_id, job)

    active_jobs = list(active_by_id.values())
    active_jobs.sort(key=lambda active: (active.created_at, active.job_id))
    return active_jobs


def _queue_message(active_count: int, running_count: int, queued_count: int) -> str:
    if active_count == 0:
        return "当前没有排队任务"
    return f"当前有 {active_count} 个转换任务，{running_count} 个正在处理，{queued_count} 个排队中"


def _cleanup_old_jobs() -> None:
    now = time.time()
    expired_paths: list[Path] = []
    with jobs_lock:
        for job_id, job in list(jobs.items()):
            if job.status in {"queued", "running"}:
                continue
            if now - job.updated_at <= JOB_TTL_SECONDS:
                continue
            expired_paths.append(job.output_path)
            del jobs[job_id]
            _remove_job_file(job_id)

    for path in expired_paths:
        _remove_file(path)

    for job in _load_all_disk_jobs():
        if job.status in {"queued", "running"}:
            continue
        if now - job.updated_at <= JOB_TTL_SECONDS:
            continue
        _remove_file(job.output_path)
        _remove_job_file(job.job_id)


def _ensure_runtime_dirs() -> None:
    JOBS_DIR.mkdir(parents=True, exist_ok=True)


def _job_file(job_id: str) -> Path:
    _ensure_runtime_dirs()
    return JOBS_DIR / f"{job_id}.json"


def _save_job(job: ConversionJob) -> None:
    with jobs_lock:
        _save_job_unlocked(job)


def _save_job_unlocked(job: ConversionJob) -> None:
    data = _job_to_json(job)
    job_file = _job_file(job.job_id)
    temp_file = job_file.with_suffix(".json.tmp")
    temp_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    os.replace(temp_file, job_file)


def _load_job_from_disk(job_id: str) -> ConversionJob | None:
    path = JOBS_DIR / f"{job_id}.json"
    if not path.exists():
        return None
    try:
        return _job_from_json(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError):
        return None


def _load_all_disk_jobs() -> list[ConversionJob]:
    if not JOBS_DIR.exists():
        return []
    jobs_from_disk = []
    for path in JOBS_DIR.glob("*.json"):
        try:
            job = _job_from_json(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError, TypeError):
            continue
        jobs_from_disk.append(job)
    return jobs_from_disk


def _remove_job_file(job_id: str) -> None:
    _remove_file(JOBS_DIR / f"{job_id}.json")


def _job_to_json(job: ConversionJob) -> dict[str, object]:
    return {
        "job_id": job.job_id,
        "status": job.status,
        "progress": job.progress,
        "message": job.message,
        "download_name": job.download_name,
        "output_path": str(job.output_path),
        "created_at": job.created_at,
        "updated_at": job.updated_at,
        "target_path": str(job.target_path) if job.target_path else "",
        "source_path": str(job.source_path) if job.source_path else "",
        "client_region": job.client_region,
        "started_at": job.started_at,
        "completed_at": job.completed_at,
        "duration_seconds": job.duration_seconds,
        "options": job.options,
        "error": job.error,
    }


def _job_from_json(data: dict[str, object]) -> ConversionJob:
    target_path = str(data.get("target_path") or "")
    source_path = str(data.get("source_path") or "")
    return ConversionJob(
        job_id=str(data["job_id"]),
        status=str(data["status"]),
        progress=int(data["progress"]),
        message=str(data["message"]),
        download_name=str(data["download_name"]),
        output_path=Path(str(data["output_path"])),
        created_at=float(data["created_at"]),
        updated_at=float(data["updated_at"]),
        target_path=Path(target_path) if target_path else None,
        source_path=Path(source_path) if source_path else None,
        client_region=str(data.get("client_region") or ""),
        started_at=_optional_float(data.get("started_at")),
        completed_at=_optional_float(data.get("completed_at")),
        duration_seconds=_optional_float(data.get("duration_seconds")),
        options=dict(data.get("options") or {}),
        error=str(data.get("error") or ""),
    )


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    return float(value)


def _record_recent_conversion(job: ConversionJob) -> None:
    if job.duration_seconds is None:
        return
    _ensure_runtime_dirs()
    payload = _recent_conversion_from_job(job)
    recent_conversions = [
        item
        for item in _recent_conversions_payload()
        if item.get("completed_at") != payload["completed_at"]
        or item.get("download_name") != payload["download_name"]
    ]
    recent_conversions.append(payload)
    recent_conversions.sort(key=lambda item: float(item.get("completed_at") or 0), reverse=True)
    recent_conversions = recent_conversions[:RECENT_CONVERSION_LIMIT]
    temp_file = RECENT_CONVERSION_FILE.with_suffix(".json.tmp")
    temp_file.write_text(json.dumps(recent_conversions, ensure_ascii=False), encoding="utf-8")
    os.replace(temp_file, RECENT_CONVERSION_FILE)


def _recent_conversion_from_job(job: ConversionJob) -> dict[str, object]:
    return {
        "region": job.client_region or "未知地区",
        "duration_seconds": round(job.duration_seconds or 0, 1),
        "completed_at": job.completed_at or time.time(),
        "download_name": job.download_name,
    }


def _recent_conversion_payload() -> dict[str, object] | None:
    recent_conversions = _recent_conversions_payload()
    return recent_conversions[0] if recent_conversions else None


def _recent_conversions_payload() -> list[dict[str, object]]:
    if not RECENT_CONVERSION_FILE.exists():
        return []
    try:
        data = json.loads(RECENT_CONVERSION_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []

    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        return []

    recent_conversions = [item for item in data if isinstance(item, dict)]
    recent_conversions.sort(key=lambda item: float(item.get("completed_at") or 0), reverse=True)
    return recent_conversions[:RECENT_CONVERSION_LIMIT]


def _client_region(request: Request) -> str:
    headers = request.headers
    city = (
        headers.get("cf-ipcity")
        or headers.get("x-client-city")
        or headers.get("x-geo-city")
    )
    country = (
        headers.get("cf-ipcountry")
        or headers.get("x-client-country")
        or headers.get("x-geo-country")
    )
    region = (
        headers.get("cf-region")
        or headers.get("x-client-region")
        or headers.get("x-geo-region")
    )
    location = " ".join(part for part in (country, region, city) if part)
    if location:
        return location

    forwarded_for = headers.get("x-forwarded-for", "")
    client_ip = forwarded_for.split(",", 1)[0].strip()
    if not client_ip:
        client_ip = headers.get("x-real-ip", "").strip()
    if not client_ip and request.client:
        client_ip = request.client.host
    return _client_ip_label(client_ip)


def _client_ip_label(value: str) -> str:
    if not value:
        return "未知地区"
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return "未知地区"
    if address.is_private or address.is_loopback or address.is_link_local:
        return "本地/内网"
    if address.version == 4:
        first, second, *_ = value.split(".")
        return f"IP {first}.{second}.*.*"
    groups = address.exploded.split(":")
    return f"IP {groups[0]}:{groups[1]}:****"


def _temporary_ttf_path() -> Path:
    _ensure_runtime_dirs()
    handle = tempfile.NamedTemporaryFile(delete=False, suffix=".ttf", dir=RUNTIME_DIR)
    try:
        return Path(handle.name)
    finally:
        handle.close()


def _remove_file(path: Path) -> None:
    try:
        os.remove(path)
    except FileNotFoundError:
        pass


def _remove_optional_file(path: Path | None) -> None:
    if path is not None:
        _remove_file(path)


def _download_name(
    source_filename: str,
    scale_percent: int,
    weight_mode: str,
    effect_x_units: float,
    effect_y_units: float,
    spacing_left_percent: float,
    spacing_right_percent: float,
    spacing_top_percent: float,
    spacing_bottom_percent: float,
    replacement_scope: str = "",
) -> str:
    normalized_source = source_filename.replace("\\", "/")
    source_stem = Path(normalized_source).stem.strip() or "font"
    safe_stem = _safe_file_part(source_stem) or "font"
    effect = _effect_label(weight_mode, effect_x_units, effect_y_units)
    replacement = _replacement_label(replacement_scope)
    spacing = _spacing_label(
        spacing_left_percent,
        spacing_right_percent,
        spacing_top_percent,
        spacing_bottom_percent,
    )
    return f"{safe_stem}-{scale_percent}pct-{effect}{replacement}{spacing}.ttf"


def _effect_label(weight_mode: str, effect_x_units: float, effect_y_units: float) -> str:
    if weight_mode == "none":
        return "none"
    if effect_x_units == effect_y_units:
        return f"{weight_mode}-u{_format_effect_number(effect_x_units)}"
    return (
        f"{weight_mode}-"
        f"x{_format_effect_number(effect_x_units)}-"
        f"y{_format_effect_number(effect_y_units)}"
    )


def _replacement_label(replacement_scope: str) -> str:
    if not replacement_scope:
        return ""
    return f"-replace-{_safe_file_part(replacement_scope) or 'custom'}"


def _spacing_label(
    spacing_left_percent: float,
    spacing_right_percent: float,
    spacing_top_percent: float,
    spacing_bottom_percent: float,
) -> str:
    if not any(
        [
            spacing_left_percent,
            spacing_right_percent,
            spacing_top_percent,
            spacing_bottom_percent,
        ]
    ):
        return ""

    return (
        "-space-"
        f"l{_format_effect_number(spacing_left_percent)}-"
        f"r{_format_effect_number(spacing_right_percent)}-"
        f"t{_format_effect_number(spacing_top_percent)}-"
        f"b{_format_effect_number(spacing_bottom_percent)}"
    )


def _format_effect_number(value: float) -> str:
    if value == int(value):
        return str(int(value))
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _safe_file_part(value: str) -> str:
    safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value)
    return safe.strip().strip(". ")


def _resolve_effect_form_values(
    effect_units: float | None,
    effect_x_units: float | None,
    effect_y_units: float | None,
    legacy_effect_x: float | None,
    legacy_effect_y: float | None,
) -> tuple[float, float]:
    if effect_units is not None:
        return effect_units, effect_units
    return (
        _resolve_legacy_effect_form_value(effect_x_units, legacy_effect_x),
        _resolve_legacy_effect_form_value(effect_y_units, legacy_effect_y),
    )


def _resolve_legacy_effect_form_value(effect_units: float | None, legacy_effect_value: float | None) -> float:
    if effect_units is not None:
        return effect_units
    if legacy_effect_value is not None:
        return legacy_effect_value
    return 0
