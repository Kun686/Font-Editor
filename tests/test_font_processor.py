from io import BytesIO

import pytest
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont

from font_processor import FontConversionError, convert_ttf


def _load_font(data: bytes) -> TTFont:
    return TTFont(BytesIO(data))


def _save_font(font: TTFont) -> bytes:
    output = BytesIO()
    font.save(output)
    return output.getvalue()


def _glyph_bounds(font: TTFont, glyph_name: str = "A") -> tuple[int, int, int, int]:
    glyph = font["glyf"][glyph_name]
    glyph.recalcBounds(font["glyf"])
    return glyph.xMin, glyph.yMin, glyph.xMax, glyph.yMax


def _glyph_contour_bounds(font: TTFont, glyph_name: str) -> list[tuple[int, int, int, int]]:
    glyph = font["glyf"][glyph_name]
    contours = []
    start = 0
    for end in glyph.endPtsOfContours:
        points = glyph.coordinates[start : end + 1]
        xs = [x for x, _ in points]
        ys = [y for _, y in points]
        contours.append((min(xs), min(ys), max(xs), max(ys)))
        start = end + 1
    return sorted(contours)


def _hollow_square_font() -> bytes:
    pen = TTGlyphPen(None)
    pen.moveTo((0, 0))
    pen.lineTo((1000, 0))
    pen.lineTo((1000, 1000))
    pen.lineTo((0, 1000))
    pen.closePath()
    pen.moveTo((400, 200))
    pen.lineTo((400, 800))
    pen.lineTo((600, 800))
    pen.lineTo((600, 200))
    pen.closePath()

    builder = FontBuilder(1000, isTTF=True)
    builder.setupGlyphOrder([".notdef", "O"])
    builder.setupCharacterMap({79: "O"})
    builder.setupGlyf({".notdef": TTGlyphPen(None).glyph(), "O": pen.glyph()})
    builder.setupHorizontalMetrics({".notdef": (1000, 0), "O": (1000, 0)})
    builder.setupHorizontalHeader(ascent=1000, descent=0)
    builder.setupNameTable(
        {
            "familyName": "HollowFont",
            "styleName": "Regular",
            "uniqueFontIdentifier": "HollowFont Regular",
            "fullName": "HollowFont Regular",
            "psName": "HollowFont-Regular",
        }
    )
    builder.setupOS2(sTypoAscender=1000, sTypoDescender=0, usWinAscent=1000, usWinDescent=0)
    builder.setupPost()
    return _save_font(builder.font)


def test_scale_changes_metrics_and_keeps_units_per_em(sample_ttf_bytes):
    converted = convert_ttf(sample_ttf_bytes, scale_percent=150)
    font = _load_font(converted)

    assert font["head"].unitsPerEm == 1000
    assert font["hmtx"].metrics["A"][0] == 750
    assert font["hmtx"].metrics["A"][1] == 75
    assert font["hhea"].ascent == 1200
    assert font["OS/2"].sTypoAscender == 1200


def test_scale_updates_supporting_font_metrics(sample_ttf_bytes):
    source = _load_font(sample_ttf_bytes)
    source["OS/2"].xAvgCharWidth = 420
    source["post"].underlinePosition = -80
    source["post"].underlineThickness = 40

    converted = convert_ttf(_save_font(source), scale_percent=150)
    font = _load_font(converted)

    assert font["OS/2"].xAvgCharWidth == 630
    assert font["post"].underlinePosition == -120
    assert font["post"].underlineThickness == 60


def test_layout_spacing_adjusts_horizontal_and_vertical_metrics(sample_ttf_bytes):
    converted = convert_ttf(
        sample_ttf_bytes,
        scale_percent=100,
        spacing_left_percent=2,
        spacing_right_percent=3,
        spacing_top_percent=4,
        spacing_bottom_percent=5,
    )
    font = _load_font(converted)

    assert font["hmtx"].metrics["A"] == (550, 70)
    assert font["hhea"].ascent == 840
    assert font["hhea"].descent == -250
    assert font["OS/2"].sTypoAscender == 840
    assert font["OS/2"].sTypoDescender == -250
    assert font["OS/2"].usWinAscent == 840
    assert font["OS/2"].usWinDescent == 250


def test_bold_effect_expands_horizontal_and_vertical_bounds(sample_ttf_bytes):
    converted = convert_ttf(
        sample_ttf_bytes,
        scale_percent=100,
        weight_mode="bold",
        effect_x_percent=5,
        effect_y_percent=7,
    )
    font = _load_font(converted)

    assert "A" in font.getGlyphOrder()
    assert _glyph_bounds(font) == (0, -70, 500, 570)
    assert font["hmtx"].metrics["A"][0] == 600


def test_bold_effect_offsets_holes_inward_instead_of_scaling_from_center():
    converted = convert_ttf(
        _hollow_square_font(),
        scale_percent=100,
        weight_mode="bold",
        effect_x_percent=5,
        effect_y_percent=5,
    )
    font = _load_font(converted)

    assert _glyph_contour_bounds(font, "O") == [
        (-50, -50, 1050, 1050),
        (450, 250, 550, 750),
    ]


def test_thin_effect_contracts_horizontal_and_vertical_bounds(sample_ttf_bytes):
    converted = convert_ttf(
        sample_ttf_bytes,
        scale_percent=100,
        weight_mode="thin",
        effect_x_percent=3,
        effect_y_percent=4,
    )
    font = _load_font(converted)

    assert "A" in font.getGlyphOrder()
    assert _glyph_bounds(font) == (80, 40, 420, 460)
    assert font["hmtx"].metrics["A"][0] == 440


@pytest.mark.parametrize("scale", [0, 9, 301, 1000])
def test_rejects_scale_outside_supported_range(sample_ttf_bytes, scale):
    with pytest.raises(FontConversionError):
        convert_ttf(sample_ttf_bytes, scale_percent=scale)


@pytest.mark.parametrize("weight_mode", ["heavy", "", "BOLD"])
def test_rejects_unknown_weight_mode(sample_ttf_bytes, weight_mode):
    with pytest.raises(FontConversionError):
        convert_ttf(sample_ttf_bytes, scale_percent=100, weight_mode=weight_mode)


@pytest.mark.parametrize("effect", [-51, 51])
def test_rejects_extreme_effect_values(sample_ttf_bytes, effect):
    with pytest.raises(FontConversionError):
        convert_ttf(
            sample_ttf_bytes,
            scale_percent=100,
            weight_mode="bold",
            effect_x_percent=effect,
        )


@pytest.mark.parametrize("spacing", [-51, 51])
def test_rejects_extreme_spacing_values(sample_ttf_bytes, spacing):
    with pytest.raises(FontConversionError):
        convert_ttf(
            sample_ttf_bytes,
            scale_percent=100,
            spacing_left_percent=spacing,
        )


def test_rejects_empty_font_bytes():
    with pytest.raises(FontConversionError):
        convert_ttf(b"", scale_percent=100)
