# Server Font Converter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a FastAPI web tool that uploads `.ttf` fonts, scales them by percentage, optionally emboldens them, and returns a converted `.ttf` without permanent storage.

**Architecture:** The app has a thin FastAPI layer and a pure conversion module. Tests exercise conversion behavior directly and API validation through FastAPI's test client. The frontend is a static, deployment-friendly page served by the same app.

**Tech Stack:** Python 3, FastAPI, Uvicorn, fontTools, pytest, HTML/CSS/JavaScript.

---

## File Structure

- `requirements.txt`: Runtime and test dependencies.
- `font_processor.py`: Conversion API and validation errors.
- `main.py`: FastAPI routes, static/template serving, upload validation, and download response.
- `templates/index.html`: Main UI.
- `static/styles.css`: Responsive styling.
- `static/app.js`: Form submission and download handling.
- `tests/conftest.py`: Synthetic TTF fixture builder.
- `tests/test_font_processor.py`: Unit tests for conversion behavior.
- `tests/test_api.py`: API tests for upload validation and successful conversion.
- `README.md`: Local run and deployment notes.

### Task 1: Project Dependencies

**Files:**
- Create: `requirements.txt`

- [ ] **Step 1: Create dependency list**

```txt
fastapi==0.135.2
uvicorn[standard]==0.42.0
python-multipart==0.0.20
fonttools==4.55.3
pytest==8.3.4
httpx2==2.2.0
```

- [ ] **Step 2: Install dependencies**

Run: `python -m pip install -r requirements.txt`
Expected: packages install successfully.

### Task 2: Conversion Tests

**Files:**
- Create: `tests/conftest.py`
- Create: `tests/test_font_processor.py`

- [ ] **Step 1: Write synthetic TTF fixture helper**

```python
from io import BytesIO

import pytest
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen


def _glyph_square(width: int = 500):
    pen = TTGlyphPen(None)
    pen.moveTo((50, 0))
    pen.lineTo((450, 0))
    pen.lineTo((450, 500))
    pen.lineTo((50, 500))
    pen.closePath()
    return pen.glyph()


@pytest.fixture
def sample_ttf_bytes():
    units_per_em = 1000
    glyph_order = [".notdef", "A"]
    fb = FontBuilder(units_per_em, isTTF=True)
    fb.setupGlyphOrder(glyph_order)
    fb.setupCharacterMap({65: "A"})
    fb.setupGlyf({".notdef": TTGlyphPen(None).glyph(), "A": _glyph_square()})
    fb.setupHorizontalMetrics({".notdef": (500, 0), "A": (500, 50)})
    fb.setupHorizontalHeader(ascent=800, descent=-200)
    fb.setupNameTable({
        "familyName": "TestFont",
        "styleName": "Regular",
        "uniqueFontIdentifier": "TestFont Regular",
        "fullName": "TestFont Regular",
        "psName": "TestFont-Regular",
    })
    fb.setupOS2(sTypoAscender=800, sTypoDescender=-200, usWinAscent=800, usWinDescent=200)
    fb.setupPost()
    buffer = BytesIO()
    fb.save(buffer)
    return buffer.getvalue()
```

- [ ] **Step 2: Write failing conversion tests**

```python
from io import BytesIO

import pytest
from fontTools.ttLib import TTFont

from font_processor import FontConversionError, convert_ttf


def _load_font(data: bytes) -> TTFont:
    return TTFont(BytesIO(data))


def test_scale_changes_metrics_and_keeps_units_per_em(sample_ttf_bytes):
    converted = convert_ttf(sample_ttf_bytes, scale_percent=150, bold=False)
    font = _load_font(converted)

    assert font["head"].unitsPerEm == 1000
    assert font["hmtx"].metrics["A"][0] == 750
    assert font["hmtx"].metrics["A"][1] == 75
    assert font["hhea"].ascent == 1200
    assert font["OS/2"].sTypoAscender == 1200


def test_bold_conversion_returns_readable_ttf(sample_ttf_bytes):
    converted = convert_ttf(sample_ttf_bytes, scale_percent=100, bold=True)
    font = _load_font(converted)

    assert "A" in font.getGlyphOrder()
    assert font["hmtx"].metrics["A"][0] > 500


@pytest.mark.parametrize("scale", [0, 9, 301, 1000])
def test_rejects_scale_outside_supported_range(sample_ttf_bytes, scale):
    with pytest.raises(FontConversionError):
        convert_ttf(sample_ttf_bytes, scale_percent=scale, bold=False)


def test_rejects_empty_font_bytes():
    with pytest.raises(FontConversionError):
        convert_ttf(b"", scale_percent=100, bold=False)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/test_font_processor.py -v`
Expected: import failure because `font_processor.py` does not exist.

### Task 3: Font Processor

**Files:**
- Create: `font_processor.py`

- [ ] **Step 1: Implement minimal converter**

```python
from __future__ import annotations

from io import BytesIO

from fontTools.misc.transform import Transform
from fontTools.ttLib import TTFont, TTLibError


class FontConversionError(ValueError):
    """Raised when an uploaded font cannot be converted."""


def convert_ttf(font_bytes: bytes, scale_percent: int, bold: bool) -> bytes:
    if not font_bytes:
        raise FontConversionError("上传的字体文件为空")
    if scale_percent < 10 or scale_percent > 300:
        raise FontConversionError("缩放比例必须在 10% 到 300% 之间")

    try:
        font = TTFont(BytesIO(font_bytes), recalcBBoxes=True, recalcTimestamp=False)
    except TTLibError as exc:
        raise FontConversionError("无法读取 TTF 字体文件") from exc

    if "glyf" not in font or "hmtx" not in font:
        raise FontConversionError("当前仅支持包含 TrueType glyf 轮廓的 .ttf 字体")

    scale = scale_percent / 100
    _scale_glyphs(font, scale)
    _scale_horizontal_metrics(font, scale)
    _scale_vertical_metrics(font, scale)

    if bold:
        _embolden(font, strength=max(8, int(font["head"].unitsPerEm * 0.035)))

    output = BytesIO()
    try:
        font.save(output)
    except Exception as exc:
        raise FontConversionError("字体转换失败") from exc
    return output.getvalue()


def _scale_glyphs(font: TTFont, scale: float) -> None:
    transform = Transform().scale(scale, scale)
    glyf = font["glyf"]
    for glyph_name in font.getGlyphOrder():
        glyph = glyf[glyph_name]
        if glyph.isComposite():
            for component in glyph.components:
                component.transform = _scale_component_transform(component.transform, scale)
                component.x = _round(component.x * scale)
                component.y = _round(component.y * scale)
        elif glyph.numberOfContours > 0:
            glyph.transform(transform, glyf)
    glyf.compile(font)


def _scale_component_transform(transform, scale: float):
    if transform is None:
        return (scale, 0, 0, scale)
    xx, xy, yx, yy = transform
    return (xx * scale, xy * scale, yx * scale, yy * scale)


def _scale_horizontal_metrics(font: TTFont, scale: float) -> None:
    hmtx = font["hmtx"]
    hmtx.metrics = {
        name: (_round(advance * scale), _round(lsb * scale))
        for name, (advance, lsb) in hmtx.metrics.items()
    }


def _scale_vertical_metrics(font: TTFont, scale: float) -> None:
    for table_tag, fields in {
        "hhea": ["ascent", "descent", "lineGap"],
        "OS/2": [
            "sTypoAscender",
            "sTypoDescender",
            "sTypoLineGap",
            "usWinAscent",
            "usWinDescent",
            "sxHeight",
            "sCapHeight",
        ],
    }.items():
        if table_tag not in font:
            continue
        table = font[table_tag]
        for field in fields:
            if hasattr(table, field):
                setattr(table, field, _round(getattr(table, field) * scale))


def _embolden(font: TTFont, strength: int) -> None:
    glyf = font["glyf"]
    for glyph_name in font.getGlyphOrder():
        glyph = glyf[glyph_name]
        if glyph.isComposite() or glyph.numberOfContours <= 0:
            continue
        glyph.expand(glyf)
        glyph.coordinates.translate((strength // 2, 0))
        glyph.coordinates.toInt()
    hmtx = font["hmtx"]
    hmtx.metrics = {
        name: (advance + strength, lsb)
        for name, (advance, lsb) in hmtx.metrics.items()
    }


def _round(value: float) -> int:
    return int(round(value))
```

- [ ] **Step 2: Run converter tests**

Run: `python -m pytest tests/test_font_processor.py -v`
Expected: all font processor tests pass.

### Task 4: API Tests

**Files:**
- Create: `tests/test_api.py`

- [ ] **Step 1: Write failing API tests**

```python
from io import BytesIO

from fastapi.testclient import TestClient
from fontTools.ttLib import TTFont

from main import app


client = TestClient(app)


def test_convert_endpoint_returns_ttf_download(sample_ttf_bytes):
    response = client.post(
        "/api/convert",
        data={"scale_percent": "125", "bold": "true"},
        files={"font_file": ("demo.ttf", sample_ttf_bytes, "font/ttf")},
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "font/ttf"
    assert "attachment" in response.headers["content-disposition"]
    font = TTFont(BytesIO(response.content))
    assert font["hmtx"].metrics["A"][0] > 500


def test_convert_endpoint_rejects_non_ttf(sample_ttf_bytes):
    response = client.post(
        "/api/convert",
        data={"scale_percent": "100", "bold": "false"},
        files={"font_file": ("demo.otf", sample_ttf_bytes, "font/otf")},
    )

    assert response.status_code == 400
    assert "只支持 .ttf" in response.json()["detail"]


def test_convert_endpoint_rejects_invalid_scale(sample_ttf_bytes):
    response = client.post(
        "/api/convert",
        data={"scale_percent": "500", "bold": "false"},
        files={"font_file": ("demo.ttf", sample_ttf_bytes, "font/ttf")},
    )

    assert response.status_code == 400
    assert "缩放比例" in response.json()["detail"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_api.py -v`
Expected: import failure because `main.py` does not exist.

### Task 5: FastAPI App

**Files:**
- Create: `main.py`
- Create: `templates/index.html`
- Create: `static/styles.css`
- Create: `static/app.js`

- [ ] **Step 1: Implement FastAPI app**

Create an app with `GET /` serving `templates/index.html`, `POST /api/convert` accepting `font_file`, `scale_percent`, and `bold`, then returning converted bytes with content type `font/ttf`.

- [ ] **Step 2: Add frontend**

Create a compact upload form with scale input, bold checkbox, submit button, progress text, error display, and browser download behavior.

- [ ] **Step 3: Run API tests**

Run: `python -m pytest tests/test_api.py -v`
Expected: all API tests pass.

### Task 6: Documentation and Full Verification

**Files:**
- Create: `README.md`

- [ ] **Step 1: Document local run and deployment**

Include commands for installing dependencies, running tests, starting Uvicorn, and an Nginx deployment note.

- [ ] **Step 2: Run full test suite**

Run: `python -m pytest -v`
Expected: all tests pass.

- [ ] **Step 3: Start local server**

Run: `python -m uvicorn main:app --host 127.0.0.1 --port 8000`
Expected: server listens at `http://127.0.0.1:8000`.
