from __future__ import annotations

import os
from pathlib import Path
import re
import tempfile
from urllib.parse import quote

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles

from font_processor import FontConversionError, replacement_characters, write_processed_ttf


BASE_DIR = Path(__file__).resolve().parent
MAX_UPLOAD_BYTES = 50 * 1024 * 1024

app = FastAPI(title="TTF 字体转换工具")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    html = (BASE_DIR / "templates" / "index.html").read_text(encoding="utf-8")
    return HTMLResponse(html)


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

    font_bytes = await _read_upload_bytes(font_file)
    if len(font_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="字体文件不能超过 50MB")

    source_font_bytes = None
    if replacement_enabled and source_font_file:
        source_font_bytes = await _read_upload_bytes(source_font_file)
        if not source_font_bytes:
            raise HTTPException(status_code=400, detail="来源字体文件为空")
        if len(source_font_bytes) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="来源字体文件不能超过 50MB")

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

    output_path = _temporary_ttf_path()
    try:
        with output_path.open("wb") as output_file:
            write_processed_ttf(
                font_bytes,
                output_file,
                scale_percent=scale_percent,
                weight_mode=weight_mode,
                effect_units=effect_units,
                effect_x_units=effect_x,
                effect_y_units=effect_y,
                spacing_left_percent=spacing_left_percent,
                spacing_right_percent=spacing_right_percent,
                spacing_top_percent=spacing_top_percent,
                spacing_bottom_percent=spacing_bottom_percent,
                source_font_bytes=source_font_bytes,
                replacement_chars=replacement_chars,
            )
    except FontConversionError as exc:
        _remove_file(output_path)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        _remove_file(output_path)
        raise

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


def _temporary_ttf_path() -> Path:
    handle = tempfile.NamedTemporaryFile(delete=False, suffix=".ttf")
    try:
        return Path(handle.name)
    finally:
        handle.close()


def _remove_file(path: Path) -> None:
    try:
        os.remove(path)
    except FileNotFoundError:
        pass


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


async def _read_upload_bytes(upload: UploadFile) -> bytes:
    try:
        return await upload.read(MAX_UPLOAD_BYTES + 1)
    finally:
        await upload.close()


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
