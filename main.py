from __future__ import annotations

from pathlib import Path
import re
from urllib.parse import quote

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles

from font_processor import FontConversionError, convert_ttf


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
    font_file: UploadFile = File(...),
    scale_percent: int = Form(100),
    weight_mode: str = Form("none"),
    effect_x_percent: float = Form(0),
    effect_y_percent: float = Form(0),
) -> Response:
    filename = font_file.filename or ""
    if not filename.lower().endswith(".ttf"):
        raise HTTPException(status_code=400, detail="只支持 .ttf 字体文件")

    try:
        font_bytes = await font_file.read(MAX_UPLOAD_BYTES + 1)
    finally:
        await font_file.close()

    if len(font_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="字体文件不能超过 50MB")

    try:
        converted = convert_ttf(
            font_bytes,
            scale_percent=scale_percent,
            weight_mode=weight_mode,
            effect_x_percent=effect_x_percent,
            effect_y_percent=effect_y_percent,
        )
    except FontConversionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    download_name = _download_name(
        filename,
        scale_percent=scale_percent,
        weight_mode=weight_mode,
        effect_x_percent=effect_x_percent,
        effect_y_percent=effect_y_percent,
    )
    return Response(
        content=converted,
        media_type="font/ttf",
        headers={
            "Content-Disposition": (
                "attachment; filename=converted.ttf; "
                f"filename*=UTF-8''{quote(download_name)}"
            ),
            "Cache-Control": "no-store",
        },
    )


def _download_name(
    source_filename: str,
    scale_percent: int,
    weight_mode: str,
    effect_x_percent: float,
    effect_y_percent: float,
) -> str:
    normalized_source = source_filename.replace("\\", "/")
    source_stem = Path(normalized_source).stem.strip() or "font"
    safe_stem = _safe_file_part(source_stem) or "font"
    effect = _effect_label(weight_mode, effect_x_percent, effect_y_percent)
    return f"{safe_stem}-{scale_percent}pct-{effect}.ttf"


def _effect_label(weight_mode: str, effect_x_percent: float, effect_y_percent: float) -> str:
    if weight_mode == "none":
        return "none"
    return (
        f"{weight_mode}-"
        f"x{_format_effect_number(effect_x_percent)}-"
        f"y{_format_effect_number(effect_y_percent)}"
    )


def _format_effect_number(value: float) -> str:
    if value == int(value):
        return str(int(value))
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _safe_file_part(value: str) -> str:
    safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value)
    return safe.strip().strip(". ")
