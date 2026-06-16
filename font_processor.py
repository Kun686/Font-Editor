from __future__ import annotations

from copy import deepcopy
from io import BytesIO
from typing import BinaryIO

from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont, TTLibError


MIN_SCALE_PERCENT = 10
MAX_SCALE_PERCENT = 300
MIN_EFFECT_UNITS = 0
MAX_EFFECT_UNITS = 500
MIN_SPACING_PERCENT = -50
MAX_SPACING_PERCENT = 50
BOLD_OVERLAY_MAX_GLYPHS = 6000
WEIGHT_MODES = {"none", "thin", "bold"}
REPLACEMENT_SCOPES = {
    "digits": "0123456789",
    "uppercase": "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
    "lowercase": "abcdefghijklmnopqrstuvwxyz",
    "letters": "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz",
    "digits_letters": "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz",
    "custom": "",
}


class FontConversionError(ValueError):
    """Raised when an uploaded font cannot be converted."""


def convert_ttf(
    font_bytes: bytes,
    scale_percent: int,
    weight_mode: str = "none",
    effect_units: float | None = None,
    effect_x_units: float | None = None,
    effect_y_units: float | None = None,
    spacing_left_percent: float = 0,
    spacing_right_percent: float = 0,
    spacing_top_percent: float = 0,
    spacing_bottom_percent: float = 0,
    effect_x_percent: float | None = None,
    effect_y_percent: float | None = None,
) -> bytes:
    font = _load_font(font_bytes)
    _apply_ttf_conversion(
        font,
        scale_percent=scale_percent,
        weight_mode=weight_mode,
        effect_units=effect_units,
        effect_x_units=effect_x_units,
        effect_y_units=effect_y_units,
        spacing_left_percent=spacing_left_percent,
        spacing_right_percent=spacing_right_percent,
        spacing_top_percent=spacing_top_percent,
        spacing_bottom_percent=spacing_bottom_percent,
        effect_x_percent=effect_x_percent,
        effect_y_percent=effect_y_percent,
    )
    return _save_font(font, "字体转换失败")


def process_ttf(
    font_bytes: bytes,
    scale_percent: int,
    weight_mode: str = "none",
    effect_units: float | None = None,
    effect_x_units: float | None = None,
    effect_y_units: float | None = None,
    spacing_left_percent: float = 0,
    spacing_right_percent: float = 0,
    spacing_top_percent: float = 0,
    spacing_bottom_percent: float = 0,
    source_font_bytes: bytes | None = None,
    replacement_chars: str = "",
    effect_x_percent: float | None = None,
    effect_y_percent: float | None = None,
) -> bytes:
    font = _build_processed_ttf_font(
        font_bytes,
        scale_percent=scale_percent,
        weight_mode=weight_mode,
        effect_units=effect_units,
        effect_x_units=effect_x_units,
        effect_y_units=effect_y_units,
        spacing_left_percent=spacing_left_percent,
        spacing_right_percent=spacing_right_percent,
        spacing_top_percent=spacing_top_percent,
        spacing_bottom_percent=spacing_bottom_percent,
        source_font_bytes=source_font_bytes,
        replacement_chars=replacement_chars,
        effect_x_percent=effect_x_percent,
        effect_y_percent=effect_y_percent,
    )
    return _save_font(font, "字体转换失败")


def write_processed_ttf(
    font_bytes: bytes,
    output_file: BinaryIO,
    scale_percent: int,
    weight_mode: str = "none",
    effect_units: float | None = None,
    effect_x_units: float | None = None,
    effect_y_units: float | None = None,
    spacing_left_percent: float = 0,
    spacing_right_percent: float = 0,
    spacing_top_percent: float = 0,
    spacing_bottom_percent: float = 0,
    source_font_bytes: bytes | None = None,
    replacement_chars: str = "",
    effect_x_percent: float | None = None,
    effect_y_percent: float | None = None,
) -> None:
    font = _build_processed_ttf_font(
        font_bytes,
        scale_percent=scale_percent,
        weight_mode=weight_mode,
        effect_units=effect_units,
        effect_x_units=effect_x_units,
        effect_y_units=effect_y_units,
        spacing_left_percent=spacing_left_percent,
        spacing_right_percent=spacing_right_percent,
        spacing_top_percent=spacing_top_percent,
        spacing_bottom_percent=spacing_bottom_percent,
        source_font_bytes=source_font_bytes,
        replacement_chars=replacement_chars,
        effect_x_percent=effect_x_percent,
        effect_y_percent=effect_y_percent,
    )
    _save_font_to_file(font, output_file, "字体转换失败")


def _build_processed_ttf_font(
    font_bytes: bytes,
    scale_percent: int,
    weight_mode: str = "none",
    effect_units: float | None = None,
    effect_x_units: float | None = None,
    effect_y_units: float | None = None,
    spacing_left_percent: float = 0,
    spacing_right_percent: float = 0,
    spacing_top_percent: float = 0,
    spacing_bottom_percent: float = 0,
    source_font_bytes: bytes | None = None,
    replacement_chars: str = "",
    effect_x_percent: float | None = None,
    effect_y_percent: float | None = None,
) -> TTFont:
    font = _load_font(font_bytes)
    if source_font_bytes is not None:
        _replace_ttf_characters_in_font(source_font_bytes, font, replacement_chars)
    _apply_ttf_conversion(
        font,
        scale_percent=scale_percent,
        weight_mode=weight_mode,
        effect_units=effect_units,
        effect_x_units=effect_x_units,
        effect_y_units=effect_y_units,
        spacing_left_percent=spacing_left_percent,
        spacing_right_percent=spacing_right_percent,
        spacing_top_percent=spacing_top_percent,
        spacing_bottom_percent=spacing_bottom_percent,
        effect_x_percent=effect_x_percent,
        effect_y_percent=effect_y_percent,
    )
    return font


def _apply_ttf_conversion(
    font: TTFont,
    scale_percent: int,
    weight_mode: str = "none",
    effect_units: float | None = None,
    effect_x_units: float | None = None,
    effect_y_units: float | None = None,
    spacing_left_percent: float = 0,
    spacing_right_percent: float = 0,
    spacing_top_percent: float = 0,
    spacing_bottom_percent: float = 0,
    effect_x_percent: float | None = None,
    effect_y_percent: float | None = None,
) -> None:
    effect_x_units, effect_y_units = _resolve_effect_unit_pair(
        effect_units,
        effect_x_units,
        effect_y_units,
        effect_x_percent,
        effect_y_percent,
    )

    if scale_percent < MIN_SCALE_PERCENT or scale_percent > MAX_SCALE_PERCENT:
        raise FontConversionError("缩放比例必须在 10% 到 300% 之间")
    if weight_mode not in WEIGHT_MODES:
        raise FontConversionError("字形效果必须是 none、thin 或 bold")
    _validate_effect_value(effect_x_units)
    _validate_effect_value(effect_y_units)
    _validate_spacing_value(spacing_left_percent)
    _validate_spacing_value(spacing_right_percent)
    _validate_spacing_value(spacing_top_percent)
    _validate_spacing_value(spacing_bottom_percent)

    if "glyf" not in font or "hmtx" not in font:
        raise FontConversionError("当前仅支持包含 TrueType glyf 轮廓的 .ttf 字体")

    scale = scale_percent / 100
    _scale_glyf_table(font, scale)
    _scale_gvar_table(font, scale)
    _scale_cvt_table(font, scale)
    _scale_horizontal_metrics(font, scale)
    _scale_vertical_metrics(font, scale)
    _scale_kern_table(font, scale)

    if weight_mode != "none":
        _apply_weight_effect(
            font,
            mode=weight_mode,
            effect_x=_round(effect_x_units),
            effect_y=_round(effect_y_units),
        )

    _apply_layout_spacing(
        font,
        left=_spacing_to_units(font, spacing_left_percent),
        right=_spacing_to_units(font, spacing_right_percent),
        top=_spacing_to_units(font, spacing_top_percent),
        bottom=_spacing_to_units(font, spacing_bottom_percent),
    )


def replacement_characters(scope: str, custom_chars: str) -> str:
    if scope not in REPLACEMENT_SCOPES:
        raise FontConversionError("替换范围必须是 digits、uppercase、lowercase、letters、digits_letters 或 custom")
    return _unique_chars(REPLACEMENT_SCOPES[scope] + (custom_chars or ""))


def replace_ttf_characters(source_font_bytes: bytes, target_font_bytes: bytes, characters: str) -> bytes:
    if not source_font_bytes:
        raise FontConversionError("来源字体文件为空")
    if not target_font_bytes:
        raise FontConversionError("目标字体文件为空")

    target = _load_font(target_font_bytes)
    _replace_ttf_characters_in_font(source_font_bytes, target, characters)
    return _save_font(target, "字体字符替换失败")


def _replace_ttf_characters_in_font(source_font_bytes: bytes, target: TTFont, characters: str) -> None:
    source = _load_font(source_font_bytes)
    _require_replaceable_font(source)
    _require_replaceable_font(target)

    source_cmap = source.getBestCmap() or {}
    target_glyf = target["glyf"]
    glyph_order = target.getGlyphOrder()
    scale = target["head"].unitsPerEm / source["head"].unitsPerEm

    for character in _unique_chars(characters):
        source_glyph_name = source_cmap.get(ord(character))
        if not source_glyph_name:
            continue

        target_glyph_name = _replacement_glyph_name(ord(character))
        if target_glyph_name not in glyph_order:
            glyph_order.append(target_glyph_name)

        glyph = _copied_simple_glyph(source["glyf"][source_glyph_name], source["glyf"])
        _scale_copied_glyph(glyph, target_glyf, scale)
        target_glyf.glyphs[target_glyph_name] = glyph
        target["hmtx"].metrics[target_glyph_name] = _scaled_metric(source["hmtx"].metrics[source_glyph_name], scale)
        _map_character_to_glyph(target, ord(character), target_glyph_name)

    target.setGlyphOrder(glyph_order)
    if "maxp" in target:
        target["maxp"].numGlyphs = len(glyph_order)
    if "hhea" in target:
        target["hhea"].numberOfHMetrics = len(glyph_order)


def _scale_glyf_table(font: TTFont, scale: float) -> None:
    glyf = font["glyf"]
    for glyph_name in font.getGlyphOrder():
        glyph = glyf[glyph_name]
        glyph.expand(glyf)
        if glyph.isComposite():
            for component in glyph.components:
                component.x = _round(component.x * scale)
                component.y = _round(component.y * scale)
            glyph.tryRecalcBoundsComposite(glyf)
            continue

        if glyph.numberOfContours > 0:
            glyph.coordinates.scale((scale, scale))
            glyph.coordinates.toInt()
            glyph.recalcBounds(glyf)


def _scale_gvar_table(font: TTFont, scale: float) -> None:
    if "gvar" not in font:
        return

    for variations in font["gvar"].variations.values():
        for variation in variations:
            coordinates = variation.coordinates
            if hasattr(coordinates, "scale"):
                coordinates.scale((scale, scale))
                coordinates.toInt()
                continue

            for index, coordinate in enumerate(coordinates):
                if coordinate is None:
                    continue
                x, y = coordinate
                coordinates[index] = (_round(x * scale), _round(y * scale))


def _scale_cvt_table(font: TTFont, scale: float) -> None:
    if "cvt " not in font:
        return

    values = font["cvt "].values
    for index, value in enumerate(values):
        values[index] = _clamp_signed_16(_round(value * scale))


def _scale_horizontal_metrics(font: TTFont, scale: float) -> None:
    hmtx = font["hmtx"]
    hmtx.metrics = {
        name: (_clamp_unsigned_16(_round(advance * scale)), _clamp_signed_16(_round(lsb * scale)))
        for name, (advance, lsb) in hmtx.metrics.items()
    }


def _scale_vertical_metrics(font: TTFont, scale: float) -> None:
    if "vmtx" in font:
        vmtx = font["vmtx"]
        vmtx.metrics = {
            name: (
                _clamp_unsigned_16(_round(advance * scale)),
                _clamp_signed_16(_round(tsb * scale)),
            )
            for name, (advance, tsb) in vmtx.metrics.items()
        }

    _scale_table_fields(
        font,
        "hhea",
        ["ascent", "descent", "lineGap", "caretOffset"],
        scale,
    )
    _scale_table_fields(
        font,
        "vhea",
        ["ascent", "descent", "lineGap", "caretOffset"],
        scale,
    )
    _scale_table_fields(
        font,
        "OS/2",
        [
            "xAvgCharWidth",
            "sTypoAscender",
            "sTypoDescender",
            "sTypoLineGap",
            "usWinAscent",
            "usWinDescent",
            "sxHeight",
            "sCapHeight",
            "ySubscriptXSize",
            "ySubscriptYSize",
            "ySubscriptXOffset",
            "ySubscriptYOffset",
            "ySuperscriptXSize",
            "ySuperscriptYSize",
            "ySuperscriptXOffset",
            "ySuperscriptYOffset",
            "yStrikeoutSize",
            "yStrikeoutPosition",
        ],
        scale,
    )
    _scale_table_fields(
        font,
        "post",
        ["underlinePosition", "underlineThickness"],
        scale,
    )


def _scale_table_fields(font: TTFont, table_tag: str, fields: list[str], scale: float) -> None:
    if table_tag not in font:
        return

    table = font[table_tag]
    for field in fields:
        if not hasattr(table, field):
            continue
        value = getattr(table, field)
        if value is None:
            continue
        if field.startswith("us"):
            setattr(table, field, _clamp_unsigned_16(_round(value * scale)))
        else:
            setattr(table, field, _clamp_signed_16(_round(value * scale)))


def _scale_kern_table(font: TTFont, scale: float) -> None:
    if "kern" not in font:
        return

    for subtable in font["kern"].kernTables:
        if not hasattr(subtable, "kernTable"):
            continue
        subtable.kernTable = {
            pair: _clamp_signed_16(_round(value * scale))
            for pair, value in subtable.kernTable.items()
        }


def _load_font(font_bytes: bytes) -> TTFont:
    if not font_bytes:
        raise FontConversionError("上传的字体文件为空")

    try:
        return TTFont(BytesIO(font_bytes), recalcBBoxes=True, recalcTimestamp=False)
    except TTLibError as exc:
        raise FontConversionError("无法读取 TTF 字体文件") from exc


def _save_font(font: TTFont, error_message: str) -> bytes:
    output = BytesIO()
    _save_font_to_file(font, output, error_message)
    return output.getvalue()


def _save_font_to_file(font: TTFont, output: BinaryIO, error_message: str) -> None:
    try:
        font.save(output)
    except Exception as exc:
        raise FontConversionError(error_message) from exc


def _require_replaceable_font(font: TTFont) -> None:
    if "glyf" not in font or "hmtx" not in font or "cmap" not in font:
        raise FontConversionError("当前仅支持包含 TrueType glyf 轮廓和 cmap 映射的 .ttf 字体")


def _unique_chars(value: str) -> str:
    seen = set()
    output = []
    for character in value:
        if character in seen:
            continue
        seen.add(character)
        output.append(character)
    return "".join(output)


def _replacement_glyph_name(codepoint: int) -> str:
    return f"replace_uni{codepoint:04X}"


def _copied_simple_glyph(source_glyph, source_glyf):
    source_glyph.expand(source_glyf)
    if source_glyph.isComposite():
        pen = TTGlyphPen(None)
        source_glyph.draw(pen, source_glyf)
        return pen.glyph()
    return deepcopy(source_glyph)


def _scale_copied_glyph(glyph, target_glyf, scale: float) -> None:
    if scale == 1:
        glyph.recalcBounds(target_glyf)
        return
    if glyph.numberOfContours > 0:
        glyph.coordinates.scale((scale, scale))
        glyph.coordinates.toInt()
        glyph.recalcBounds(target_glyf)


def _scaled_metric(metric: tuple[int, int], scale: float) -> tuple[int, int]:
    advance, side_bearing = metric
    return (
        _clamp_unsigned_16(_round(advance * scale)),
        _clamp_signed_16(_round(side_bearing * scale)),
    )


def _map_character_to_glyph(font: TTFont, codepoint: int, glyph_name: str) -> None:
    mapped = False
    for table in font["cmap"].tables:
        if not table.isUnicode():
            continue
        if table.format == 4 and codepoint > 0xFFFF:
            continue
        table.cmap[codepoint] = glyph_name
        mapped = True

    if not mapped:
        raise FontConversionError("目标字体缺少可写入的 Unicode cmap 表")


def _resolve_effect_unit_pair(
    effect_units: float | None,
    effect_x_units: float | None,
    effect_y_units: float | None,
    legacy_effect_x: float | None,
    legacy_effect_y: float | None,
) -> tuple[float, float]:
    if effect_units is not None:
        return effect_units, effect_units
    return (
        _resolve_legacy_effect_units(effect_x_units, legacy_effect_x),
        _resolve_legacy_effect_units(effect_y_units, legacy_effect_y),
    )


def _resolve_legacy_effect_units(effect_units: float | None, legacy_effect_value: float | None) -> float:
    if effect_units is not None:
        return effect_units
    if legacy_effect_value is not None:
        return legacy_effect_value
    return 0


def _validate_effect_value(value: float) -> None:
    if value < MIN_EFFECT_UNITS or value > MAX_EFFECT_UNITS:
        raise FontConversionError("效果数值必须在 0 到 500 字体单位之间")


def _validate_spacing_value(value: float) -> None:
    if value < MIN_SPACING_PERCENT or value > MAX_SPACING_PERCENT:
        raise FontConversionError("间距数值必须在 -50 到 50 之间")


def _spacing_to_units(font: TTFont, percent: float) -> int:
    return _round(font["head"].unitsPerEm * percent / 100)


def _apply_weight_effect(font: TTFont, mode: str, effect_x: int, effect_y: int) -> None:
    if effect_x == 0 and effect_y == 0:
        return

    glyf = font["glyf"]
    bold_offsets = _bold_overlay_offsets(effect_x, effect_y)
    use_overlay_bold = mode == "bold" and _uses_overlay_bold(font)
    thin_delta_x = -effect_x
    thin_delta_y = -effect_y
    composite_bold_glyphs = []
    for glyph_name in font.getGlyphOrder():
        glyph = glyf[glyph_name]
        glyph.expand(glyf)
        if not _glyph_has_drawable_outline(glyph):
            continue

        if mode == "bold":
            if use_overlay_bold:
                _append_bold_overlay(glyph, glyf, bold_offsets)
            elif glyph.isComposite():
                composite_bold_glyphs.append(glyph)
            else:
                _embolden_glyph_contours(glyph, effect_x, effect_y)
                glyph.coordinates.toInt()
                glyph.recalcBounds(glyf)
        else:
            if glyph.isComposite():
                glyph.tryRecalcBoundsComposite(glyf)
                continue
            _offset_glyph_contours(glyph, thin_delta_x, thin_delta_y)
            glyph.coordinates.toInt()
            glyph.recalcBounds(glyf)

    for glyph in composite_bold_glyphs:
        glyph.tryRecalcBoundsComposite(glyf)

    if mode == "bold":
        _adjust_synthetic_bold_metrics(font, bold_offsets)
    else:
        _adjust_horizontal_metrics(font, thin_delta_x)
    _refresh_glyph_counts(font)
    _mark_weight_style(font, mode)


def _glyph_has_drawable_outline(glyph) -> bool:
    return glyph.isComposite() or glyph.numberOfContours > 0


def _uses_overlay_bold(font: TTFont) -> bool:
    return len(font.getGlyphOrder()) <= BOLD_OVERLAY_MAX_GLYPHS


def _bold_overlay_offsets(effect_x: int, effect_y: int) -> tuple[tuple[int, int], ...]:
    offsets: list[tuple[int, int]] = []

    if effect_x:
        offsets.extend(((-effect_x, 0), (effect_x, 0)))
    if effect_y:
        offsets.extend(((0, -effect_y), (0, effect_y)))
    if effect_x and effect_y:
        diagonal_x = max(1, _round(effect_x * 0.707))
        diagonal_y = max(1, _round(effect_y * 0.707))
        offsets.extend(
            (
                (-diagonal_x, -diagonal_y),
                (diagonal_x, -diagonal_y),
                (-diagonal_x, diagonal_y),
                (diagonal_x, diagonal_y),
            )
        )

    return tuple(dict.fromkeys(offsets))


def _append_bold_overlay(glyph, glyf, offsets: tuple[tuple[int, int], ...]) -> None:
    if not offsets:
        return

    if glyph.isComposite():
        original_components = list(glyph.components)
        for offset_x, offset_y in offsets:
            for component in original_components:
                shifted = deepcopy(component)
                shifted.x = _clamp_signed_16(shifted.x + offset_x)
                shifted.y = _clamp_signed_16(shifted.y + offset_y)
                glyph.components.append(shifted)
        glyph.tryRecalcBoundsComposite(glyf)
        return

    original_coordinates = list(glyph.coordinates)
    original_flags = list(glyph.flags)
    original_end_points = list(glyph.endPtsOfContours)
    base_index = len(glyph.coordinates)

    for offset_x, offset_y in offsets:
        glyph.coordinates.extend(
            [
                (
                    _clamp_signed_16(x + offset_x),
                    _clamp_signed_16(y + offset_y),
                )
                for x, y in original_coordinates
            ]
        )
        glyph.flags.extend(original_flags)
        glyph.endPtsOfContours.extend(base_index + end_point for end_point in original_end_points)
        base_index += len(original_coordinates)

    glyph.numberOfContours = len(glyph.endPtsOfContours)
    glyph.coordinates.toInt()
    glyph.recalcBounds(glyf)


def _embolden_glyph_contours(glyph, delta_x: int, delta_y: int) -> None:
    contours = _glyph_contours(glyph)
    if not contours:
        return

    original = list(glyph.coordinates)
    contour_points = [[original[index] for index in contour] for contour in contours]
    contour_depths = _contour_depths(contour_points)
    updates = {}

    for contour, points, depth in zip(contours, contour_points, contour_depths):
        if len(points) < 2:
            continue

        xs = [x for x, _ in points]
        ys = [y for _, y in points]
        center_x = (min(xs) + max(xs)) / 2
        center_y = (min(ys) + max(ys)) / 2
        invert_for_hole = depth % 2 == 1
        for glyph_index, (x, y) in zip(contour, points):
            direction_x, direction_y = _rounded_offset_direction(
                x,
                y,
                center_x,
                center_y,
                invert_for_hole,
            )
            x, y = original[glyph_index]
            updates[glyph_index] = (
                _clamp_signed_16(_round(x + direction_x * delta_x)),
                _clamp_signed_16(_round(y + direction_y * delta_y)),
            )

    for index, point in updates.items():
        glyph.coordinates[index] = point


def _refresh_glyph_counts(font: TTFont) -> None:
    glyph_order_length = len(font.getGlyphOrder())
    if "maxp" in font:
        font["maxp"].numGlyphs = glyph_order_length
        font["maxp"].recalc(font)
    if "hhea" in font:
        font["hhea"].numberOfHMetrics = glyph_order_length


def _apply_layout_spacing(font: TTFont, left: int, right: int, top: int, bottom: int) -> None:
    if left == 0 and right == 0 and top == 0 and bottom == 0:
        return

    if left != 0 or right != 0:
        _adjust_layout_horizontal_spacing(font, left, right)
    if top != 0 or bottom != 0:
        _adjust_layout_vertical_spacing(font, top, bottom)


def _adjust_layout_horizontal_spacing(font: TTFont, left: int, right: int) -> None:
    advance_delta = left + right
    hmtx = font["hmtx"]
    hmtx.metrics = {
        name: (
            _clamp_unsigned_16(advance + advance_delta),
            _clamp_signed_16(lsb + left),
        )
        for name, (advance, lsb) in hmtx.metrics.items()
    }

    if "hhea" in font:
        hhea = font["hhea"]
        _add_table_field(hhea, "advanceWidthMax", advance_delta, unsigned=True)
        _add_table_field(hhea, "minLeftSideBearing", left)
        _add_table_field(hhea, "minRightSideBearing", right)
        _add_table_field(hhea, "xMaxExtent", left)

    if "OS/2" in font:
        _add_table_field(font["OS/2"], "xAvgCharWidth", advance_delta)


def _adjust_layout_vertical_spacing(font: TTFont, top: int, bottom: int) -> None:
    for table_tag in ("hhea", "vhea"):
        if table_tag not in font:
            continue
        table = font[table_tag]
        _add_table_field(table, "ascent", top)
        _add_table_field(table, "descent", -bottom)

    if "OS/2" in font:
        os2 = font["OS/2"]
        _add_table_field(os2, "sTypoAscender", top)
        _add_table_field(os2, "sTypoDescender", -bottom)
        _add_table_field(os2, "usWinAscent", top, unsigned=True)
        _add_table_field(os2, "usWinDescent", bottom, unsigned=True)

    if "vmtx" in font:
        advance_delta = top + bottom
        vmtx = font["vmtx"]
        vmtx.metrics = {
            name: (
                _clamp_unsigned_16(advance + advance_delta),
                _clamp_signed_16(tsb + top),
            )
            for name, (advance, tsb) in vmtx.metrics.items()
        }


def _add_table_field(table, field: str, delta: int, unsigned: bool = False) -> None:
    if not hasattr(table, field):
        return

    value = getattr(table, field)
    if value is None:
        return

    adjusted = _round(value + delta)
    if unsigned:
        adjusted = _clamp_unsigned_16(adjusted)
    else:
        adjusted = _clamp_signed_16(adjusted)
    setattr(table, field, adjusted)


def _offset_glyph_contours(glyph, delta_x: int, delta_y: int) -> None:
    contours = _glyph_contours(glyph)
    if not contours:
        return

    original = list(glyph.coordinates)
    contour_points = [[original[index] for index in contour] for contour in contours]
    contour_depths = _contour_depths(contour_points)
    updates = {}

    for contour, points, depth in zip(contours, contour_points, contour_depths):
        if len(points) < 2:
            continue

        xs = [x for x, _ in points]
        ys = [y for _, y in points]
        center_x = (min(xs) + max(xs)) / 2
        center_y = (min(ys) + max(ys)) / 2
        invert_for_hole = depth % 2 == 1
        for glyph_index, (x, y) in zip(contour, points):
            direction_x = _axis_offset_direction(x, center_x, invert_for_hole)
            direction_y = _axis_offset_direction(y, center_y, invert_for_hole)
            x, y = original[glyph_index]
            updates[glyph_index] = (
                _clamp_signed_16(_round(x + direction_x * delta_x)),
                _clamp_signed_16(_round(y + direction_y * delta_y)),
            )

    for index, point in updates.items():
        glyph.coordinates[index] = point


def _axis_offset_direction(value: int, center: float, invert: bool) -> int:
    if value == center:
        return 0
    direction = -1 if value < center else 1
    return -direction if invert else direction


def _rounded_offset_direction(
    x: int,
    y: int,
    center_x: float,
    center_y: float,
    invert: bool,
) -> tuple[float, float]:
    distance_x = x - center_x
    distance_y = y - center_y
    distance = max(abs(distance_x), abs(distance_y))
    if distance == 0:
        return 0, 0

    direction_x = distance_x / distance
    direction_y = distance_y / distance
    if invert:
        direction_x = -direction_x
        direction_y = -direction_y
    return direction_x, direction_y


def _glyph_contours(glyph) -> list[list[int]]:
    contours = []
    start = 0
    for end in glyph.endPtsOfContours:
        contours.append(list(range(start, end + 1)))
        start = end + 1
    return contours


def _contour_depths(contours: list[list[tuple[int, int]]]) -> list[int]:
    depths = []
    for index, contour in enumerate(contours):
        point = contour[0]
        depth = 0
        for other_index, other in enumerate(contours):
            if other_index == index or len(other) < 3:
                continue
            if _point_in_contour(point, other):
                depth += 1
        depths.append(depth)
    return depths


def _point_in_contour(point: tuple[int, int], contour: list[tuple[int, int]]) -> bool:
    x, y = point
    inside = False
    previous_x, previous_y = contour[-1]
    for current_x, current_y in contour:
        crosses_y = (current_y > y) != (previous_y > y)
        if crosses_y:
            crossing_x = (previous_x - current_x) * (y - current_y) / (previous_y - current_y) + current_x
            if x < crossing_x:
                inside = not inside
        previous_x, previous_y = current_x, current_y
    return inside


def _adjust_horizontal_metrics(font: TTFont, delta_x: int) -> None:
    if delta_x == 0:
        return

    hmtx = font["hmtx"]
    advance_delta = 2 * delta_x
    hmtx.metrics = {
        name: (
            _clamp_unsigned_16(advance + advance_delta),
            _clamp_signed_16(lsb - delta_x),
        )
        for name, (advance, lsb) in hmtx.metrics.items()
    }


def _adjust_synthetic_bold_metrics(font: TTFont, offsets: tuple[tuple[int, int], ...]) -> None:
    if not offsets:
        return

    left = max((abs(offset_x) for offset_x, _ in offsets if offset_x < 0), default=0)
    right = max((offset_x for offset_x, _ in offsets if offset_x > 0), default=0)
    top = max((offset_y for _, offset_y in offsets if offset_y > 0), default=0)
    bottom = max((abs(offset_y) for _, offset_y in offsets if offset_y < 0), default=0)

    if top or bottom:
        _adjust_layout_vertical_spacing(font, top, bottom)

    if left == 0 and right == 0:
        return

    hmtx = font["hmtx"]
    advance_delta = left + right
    hmtx.metrics = {
        name: (
            _clamp_unsigned_16(advance + advance_delta),
            _clamp_signed_16(lsb - left),
        )
        for name, (advance, lsb) in hmtx.metrics.items()
    }


def _mark_weight_style(font: TTFont, mode: str) -> None:
    if "head" in font:
        if mode == "bold":
            font["head"].macStyle |= 0b1
        elif mode == "thin":
            font["head"].macStyle &= ~0b1

    if "OS/2" not in font:
        return

    os2 = font["OS/2"]
    if mode == "bold":
        os2.usWeightClass = max(getattr(os2, "usWeightClass", 400), 700)
        os2.fsSelection |= 0b100000
    elif mode == "thin":
        os2.usWeightClass = min(getattr(os2, "usWeightClass", 400), 300)
        os2.fsSelection &= ~0b100000


def _round(value: float) -> int:
    return int(round(value))


def _clamp_signed_16(value: int) -> int:
    return max(-32768, min(32767, value))


def _clamp_unsigned_16(value: int) -> int:
    return max(0, min(65535, value))
