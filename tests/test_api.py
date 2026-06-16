from io import BytesIO

from fastapi.testclient import TestClient
from fontTools.ttLib import TTFont

from main import app


client = TestClient(app)


def test_convert_endpoint_returns_ttf_download(sample_ttf_bytes):
    response = client.post(
        "/api/convert",
        data={
            "scale_percent": "125",
            "weight_mode": "bold",
            "effect_units": "5",
        },
        files={"font_file": ("demo.ttf", sample_ttf_bytes, "font/ttf")},
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "font/ttf"
    assert "attachment" in response.headers["content-disposition"]
    assert "demo-125pct-bold-u5.ttf" in response.headers["content-disposition"]
    font = TTFont(BytesIO(response.content))
    assert font["hmtx"].metrics["A"][0] > 625


def test_convert_endpoint_replaces_characters_from_source_font(build_ttf_bytes):
    source = build_ttf_bytes({"1": (10, 0, 210, 400), "A": (30, 0, 430, 700)})
    target = build_ttf_bytes({"1": (60, 0, 160, 200), "B": (70, 0, 370, 500)})

    response = client.post(
        "/api/convert",
        data={
            "scale_percent": "100",
            "weight_mode": "none",
            "replacement_scope": "digits",
            "custom_replacement_chars": "A",
        },
        files={
            "font_file": ("target.ttf", target, "font/ttf"),
            "source_font_file": ("source.ttf", source, "font/ttf"),
        },
    )

    assert response.status_code == 200
    assert "target-100pct-none-replace-digits.ttf" in response.headers["content-disposition"]
    font = TTFont(BytesIO(response.content))
    cmap = font.getBestCmap()
    glyph_one = font["glyf"][cmap[ord("1")]]
    glyph_one.recalcBounds(font["glyf"])
    glyph_a = font["glyf"][cmap[ord("A")]]
    glyph_a.recalcBounds(font["glyf"])
    glyph_b = font["glyf"][cmap[ord("B")]]
    glyph_b.recalcBounds(font["glyf"])

    assert (glyph_one.xMin, glyph_one.yMin, glyph_one.xMax, glyph_one.yMax) == (10, 0, 210, 400)
    assert (glyph_a.xMin, glyph_a.yMin, glyph_a.xMax, glyph_a.yMax) == (30, 0, 430, 700)
    assert (glyph_b.xMin, glyph_b.yMin, glyph_b.xMax, glyph_b.yMax) == (70, 0, 370, 500)


def test_convert_endpoint_applies_layout_spacing(sample_ttf_bytes):
    response = client.post(
        "/api/convert",
        data={
            "scale_percent": "100",
            "weight_mode": "none",
            "spacing_left_percent": "2",
            "spacing_right_percent": "3",
            "spacing_top_percent": "4",
            "spacing_bottom_percent": "5",
        },
        files={"font_file": ("demo.ttf", sample_ttf_bytes, "font/ttf")},
    )

    assert response.status_code == 200
    assert "demo-100pct-none-space-l2-r3-t4-b5.ttf" in response.headers["content-disposition"]
    font = TTFont(BytesIO(response.content))
    assert font["hmtx"].metrics["A"] == (550, 70)
    assert font["hhea"].ascent == 840
    assert font["hhea"].descent == -250


def test_homepage_includes_spacing_controls_and_progress_bar():
    response = client.get("/")

    assert response.status_code == 200
    assert 'id="changelog-dialog"' in response.text
    assert "2026-06-16 16:10 +08:00" in response.text
    assert "上传字体后立即预览当前字符效果" in response.text
    assert "修复进度条停在 95%" in response.text
    assert "2026-06-16 16:36 +08:00" in response.text
    assert "字重强度改为单一字体单位输入" in response.text
    assert "选择要处理的字体 .ttf" in response.text
    assert "选择 B 目标字体" not in response.text
    assert "<span>水平效果" not in response.text
    assert "<span>垂直效果" not in response.text
    assert "可选：字符替换" in response.text
    assert "可选：选择 A 来源字体 .ttf" in response.text
    assert response.text.index("排版间距 (%)") < response.text.index("可选：字符替换")
    assert 'id="download-link"' in response.text
    assert 'id="clear-font-file"' in response.text
    assert 'id="clear-source-font-file"' in response.text
    assert 'id="effect-units"' in response.text
    assert 'id="spacing-left"' in response.text
    assert 'id="spacing-right"' in response.text
    assert 'id="spacing-top"' in response.text
    assert 'id="spacing-bottom"' in response.text
    assert 'id="progress-bar"' in response.text
    assert 'id="source-font-file"' in response.text
    assert 'id="replacement-scope"' in response.text
    assert 'id="custom-replacement-chars"' in response.text
    assert 'id="target-preview-output"' in response.text
    assert 'id="source-preview-output"' in response.text
    assert 'id="preview-output"' in response.text


def test_convert_endpoint_rejects_non_ttf(sample_ttf_bytes):
    response = client.post(
        "/api/convert",
        data={"scale_percent": "100", "weight_mode": "none"},
        files={"font_file": ("demo.otf", sample_ttf_bytes, "font/otf")},
    )

    assert response.status_code == 400
    assert "只支持 .ttf" in response.json()["detail"]


def test_convert_endpoint_rejects_invalid_scale(sample_ttf_bytes):
    response = client.post(
        "/api/convert",
        data={"scale_percent": "500", "weight_mode": "none"},
        files={"font_file": ("demo.ttf", sample_ttf_bytes, "font/ttf")},
    )

    assert response.status_code == 400
    assert "缩放比例" in response.json()["detail"]


def test_convert_endpoint_rejects_invalid_weight_mode(sample_ttf_bytes):
    response = client.post(
        "/api/convert",
        data={"scale_percent": "100", "weight_mode": "wide"},
        files={"font_file": ("demo.ttf", sample_ttf_bytes, "font/ttf")},
    )

    assert response.status_code == 400
    assert "字形效果" in response.json()["detail"]


def test_convert_endpoint_rejects_extreme_effect_value(sample_ttf_bytes):
    response = client.post(
        "/api/convert",
        data={
            "scale_percent": "100",
            "weight_mode": "thin",
            "effect_units": "501",
        },
        files={"font_file": ("demo.ttf", sample_ttf_bytes, "font/ttf")},
    )

    assert response.status_code == 400
    assert "效果数值" in response.json()["detail"]


def test_convert_endpoint_rejects_extreme_spacing_value(sample_ttf_bytes):
    response = client.post(
        "/api/convert",
        data={
            "scale_percent": "100",
            "weight_mode": "none",
            "spacing_left_percent": "80",
        },
        files={"font_file": ("demo.ttf", sample_ttf_bytes, "font/ttf")},
    )

    assert response.status_code == 400
    assert "间距" in response.json()["detail"]
