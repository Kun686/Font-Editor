from io import BytesIO

import pytest
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont

from font_processor import FontConversionError, convert_ttf, replace_ttf_characters, replacement_characters


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


def _custom_glyph_font(points: list[tuple[int, int]]) -> bytes:
    pen = TTGlyphPen(None)
    pen.moveTo(points[0])
    for point in points[1:]:
        pen.lineTo(point)
    pen.closePath()

    builder = FontBuilder(1000, isTTF=True)
    builder.setupGlyphOrder([".notdef", "A"])
    builder.setupCharacterMap({65: "A"})
    builder.setupGlyf({".notdef": TTGlyphPen(None).glyph(), "A": pen.glyph()})
    builder.setupHorizontalMetrics({".notdef": (500, 0), "A": (1000, 0)})
    builder.setupHorizontalHeader(ascent=800, descent=-200)
    builder.setupNameTable(
        {
            "familyName": "CustomGlyph",
            "styleName": "Regular",
            "uniqueFontIdentifier": "CustomGlyph Regular",
            "fullName": "CustomGlyph Regular",
            "psName": "CustomGlyph-Regular",
        }
    )
    builder.setupOS2(sTypoAscender=800, sTypoDescender=-200, usWinAscent=800, usWinDescent=200)
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
        effect_units=5,
    )
    font = _load_font(converted)

    assert "A" in font.getGlyphOrder()
    assert _glyph_bounds(font) == (45, -5, 455, 505)
    assert font["hmtx"].metrics["A"] == (510, 45)
    assert font["hhea"].ascent == 805
    assert font["hhea"].descent == -205


def test_bold_effect_preserves_original_outline_and_adds_rounded_overlays(sample_ttf_bytes):
    source = _load_font(sample_ttf_bytes)
    original_glyph = source["glyf"]["A"]
    original_glyph.expand(source["glyf"])
    original_coordinates = list(original_glyph.coordinates)
    original_contours = original_glyph.numberOfContours

    converted = convert_ttf(
        sample_ttf_bytes,
        scale_percent=100,
        weight_mode="bold",
        effect_units=5,
    )
    font = _load_font(converted)
    glyph = font["glyf"]["A"]
    contour_bounds = _glyph_contour_bounds(font, "A")

    assert not glyph.isComposite()
    assert glyph.numberOfContours == original_contours * 9
    assert list(glyph.coordinates[: len(original_coordinates)]) == original_coordinates
    assert (45, 0, 445, 500) in contour_bounds
    assert (55, 0, 455, 500) in contour_bounds
    assert (50, -5, 450, 495) in contour_bounds
    assert (50, 5, 450, 505) in contour_bounds
    assert (46, -4, 446, 496) in contour_bounds
    assert (54, 4, 454, 504) in contour_bounds
    assert _glyph_bounds(font) == (45, -5, 455, 505)


def test_legacy_bold_effect_expands_horizontal_and_vertical_bounds(sample_ttf_bytes):
    converted = convert_ttf(
        sample_ttf_bytes,
        scale_percent=100,
        weight_mode="bold",
        effect_x_units=5,
        effect_y_units=7,
    )
    font = _load_font(converted)

    assert "A" in font.getGlyphOrder()
    assert _glyph_bounds(font) == (45, -7, 455, 507)
    assert font["hmtx"].metrics["A"] == (510, 45)


def test_bold_effect_offsets_holes_inward_instead_of_scaling_from_center():
    converted = convert_ttf(
        _hollow_square_font(),
        scale_percent=100,
        weight_mode="bold",
        effect_x_units=5,
        effect_y_units=5,
    )
    font = _load_font(converted)
    glyph = font["glyf"]["O"]
    contour_bounds = _glyph_contour_bounds(font, "O")

    assert not glyph.isComposite()
    assert (0, 0, 1000, 1000) in contour_bounds
    assert (400, 200, 600, 800) in contour_bounds
    assert (5, 0, 1005, 1000) in contour_bounds
    assert (405, 200, 605, 800) in contour_bounds
    assert (-5, 0, 995, 1000) in contour_bounds
    assert (395, 200, 595, 800) in contour_bounds
    assert (0, -5, 1000, 995) in contour_bounds
    assert (400, 195, 600, 795) in contour_bounds
    assert (-4, -4, 996, 996) in contour_bounds
    assert (396, 196, 596, 796) in contour_bounds
    assert _glyph_bounds(font, "O") == (-5, -5, 1005, 1005)


def test_bold_effect_limits_point_movement_to_requested_units():
    source_points = [(0, 0), (500, 1), (1000, 0), (500, 800)]
    converted = convert_ttf(
        _custom_glyph_font(source_points),
        scale_percent=100,
        weight_mode="bold",
        effect_x_units=10,
        effect_y_units=10,
    )
    font = _load_font(converted)
    output_points = list(font["glyf"]["A"].coordinates[: len(source_points)])

    for (source_x, source_y), (output_x, output_y) in zip(source_points, output_points):
        assert abs(output_x - source_x) <= 10
        assert abs(output_y - source_y) <= 10


def test_thin_effect_contracts_horizontal_and_vertical_bounds(sample_ttf_bytes):
    converted = convert_ttf(
        sample_ttf_bytes,
        scale_percent=100,
        weight_mode="thin",
        effect_units=4,
    )
    font = _load_font(converted)

    assert "A" in font.getGlyphOrder()
    assert _glyph_bounds(font) == (54, 4, 446, 496)
    assert font["hmtx"].metrics["A"][0] == 492


def test_replacement_characters_builds_presets_with_custom_symbols():
    assert replacement_characters("digits", "") == "0123456789"
    assert replacement_characters("uppercase", "") == "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    assert replacement_characters("lowercase", "") == "abcdefghijklmnopqrstuvwxyz"
    assert replacement_characters("digits_letters", "+-+1") == (
        "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz+-"
    )
    assert replacement_characters("custom", "+-+1") == "+-1"


def test_replace_ttf_characters_overwrites_existing_and_adds_missing_chars(build_ttf_bytes):
    source = build_ttf_bytes(
        {
            "1": (10, 0, 210, 400),
            "2": (20, 0, 220, 420),
            "A": (30, 0, 430, 700),
        }
    )
    target = build_ttf_bytes(
        {
            "1": (60, 0, 160, 200),
            "B": (70, 0, 370, 500),
        }
    )

    converted = replace_ttf_characters(source, target, "12A")
    font = _load_font(converted)
    cmap = font.getBestCmap()

    assert _glyph_bounds(font, cmap[ord("1")]) == (10, 0, 210, 400)
    assert _glyph_bounds(font, cmap[ord("2")]) == (20, 0, 220, 420)
    assert _glyph_bounds(font, cmap[ord("A")]) == (30, 0, 430, 700)
    assert _glyph_bounds(font, cmap[ord("B")]) == (70, 0, 370, 500)
    assert font["hmtx"].metrics[cmap[ord("1")]] == (260, 10)
    assert font["hmtx"].metrics[cmap[ord("2")]] == (270, 20)


def test_replace_ttf_characters_scales_source_glyphs_to_target_units(build_ttf_bytes):
    source = build_ttf_bytes({"7": (200, 0, 1200, 1600)}, units_per_em=2000)
    target = build_ttf_bytes({"7": (50, 0, 250, 500)}, units_per_em=1000)

    converted = replace_ttf_characters(source, target, "7")
    font = _load_font(converted)
    cmap = font.getBestCmap()

    assert font["head"].unitsPerEm == 1000
    assert _glyph_bounds(font, cmap[ord("7")]) == (100, 0, 600, 800)
    assert font["hmtx"].metrics[cmap[ord("7")]] == (625, 100)


@pytest.mark.parametrize("scale", [0, 9, 301, 1000])
def test_rejects_scale_outside_supported_range(sample_ttf_bytes, scale):
    with pytest.raises(FontConversionError):
        convert_ttf(sample_ttf_bytes, scale_percent=scale)


@pytest.mark.parametrize("weight_mode", ["heavy", "", "BOLD"])
def test_rejects_unknown_weight_mode(sample_ttf_bytes, weight_mode):
    with pytest.raises(FontConversionError):
        convert_ttf(sample_ttf_bytes, scale_percent=100, weight_mode=weight_mode)


@pytest.mark.parametrize("effect", [-501, 501])
def test_rejects_extreme_effect_values(sample_ttf_bytes, effect):
    with pytest.raises(FontConversionError):
        convert_ttf(
            sample_ttf_bytes,
            scale_percent=100,
            weight_mode="bold",
            effect_units=effect,
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
