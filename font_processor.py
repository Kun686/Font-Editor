from __future__ import annotations

from io import BytesIO
from math import hypot

from fontTools.ttLib import TTFont, TTLibError


MIN_SCALE_PERCENT = 10
MAX_SCALE_PERCENT = 300
MIN_EFFECT_PERCENT = -50
MAX_EFFECT_PERCENT = 50
WEIGHT_MODES = {"none", "thin", "bold"}


class FontConversionError(ValueError):
    """Raised when an uploaded font cannot be converted."""


def convert_ttf(
    font_bytes: bytes,
    scale_percent: int,
    weight_mode: str = "none",
    effect_x_percent: float = 0,
    effect_y_percent: float = 0,
) -> bytes:
    if not font_bytes:
        raise FontConversionError("上传的字体文件为空")
    if scale_percent < MIN_SCALE_PERCENT or scale_percent > MAX_SCALE_PERCENT:
        raise FontConversionError("缩放比例必须在 10% 到 300% 之间")
    if weight_mode not in WEIGHT_MODES:
        raise FontConversionError("字形效果必须是 none、thin 或 bold")
    _validate_effect_value(effect_x_percent)
    _validate_effect_value(effect_y_percent)

    try:
        font = TTFont(BytesIO(font_bytes), recalcBBoxes=True, recalcTimestamp=False)
    except TTLibError as exc:
        raise FontConversionError("无法读取 TTF 字体文件") from exc

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
            effect_x=_effect_to_units(font, effect_x_percent),
            effect_y=_effect_to_units(font, effect_y_percent),
        )

    output = BytesIO()
    try:
        font.save(output)
    except Exception as exc:
        raise FontConversionError("字体转换失败") from exc
    return output.getvalue()


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


def _validate_effect_value(value: float) -> None:
    if value < MIN_EFFECT_PERCENT or value > MAX_EFFECT_PERCENT:
        raise FontConversionError("效果数值必须在 -50 到 50 之间")


def _effect_to_units(font: TTFont, percent: float) -> int:
    return _round(font["head"].unitsPerEm * percent / 100)


def _apply_weight_effect(font: TTFont, mode: str, effect_x: int, effect_y: int) -> None:
    if effect_x == 0 and effect_y == 0:
        return

    direction = 1 if mode == "bold" else -1
    delta_x = effect_x * direction
    delta_y = effect_y * direction

    glyf = font["glyf"]
    for glyph_name in font.getGlyphOrder():
        glyph = glyf[glyph_name]
        glyph.expand(glyf)
        if glyph.isComposite():
            glyph.tryRecalcBoundsComposite(glyf)
            continue
        if glyph.numberOfContours <= 0:
            continue

        _offset_glyph_contours(glyph, delta_x, delta_y)
        glyph.coordinates.toInt()
        glyph.recalcBounds(glyf)

    _adjust_horizontal_metrics(font, delta_x)
    _mark_weight_style(font, mode)


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

        area = _contour_area(points)
        if area == 0:
            continue

        invert_for_hole = depth % 2 == 1
        for local_index, glyph_index in enumerate(contour):
            normal = _contour_miter_normal(points, local_index, area, invert_for_hole)
            if normal is None:
                continue

            x, y = original[glyph_index]
            updates[glyph_index] = (
                _clamp_signed_16(_round(x + normal[0] * delta_x)),
                _clamp_signed_16(_round(y + normal[1] * delta_y)),
            )

    for index, point in updates.items():
        glyph.coordinates[index] = point


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


def _contour_area(points: list[tuple[int, int]]) -> float:
    area = 0.0
    for index, (x1, y1) in enumerate(points):
        x2, y2 = points[(index + 1) % len(points)]
        area += x1 * y2 - x2 * y1
    return area / 2


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


def _contour_miter_normal(
    points: list[tuple[int, int]],
    index: int,
    area: float,
    invert_for_hole: bool,
) -> tuple[float, float] | None:
    previous = _distinct_contour_point(points, index, -1)
    current = points[index]
    next_point = _distinct_contour_point(points, index, 1)
    if previous is None or next_point is None:
        return None

    incoming = _segment_fill_outward_normal(previous, current, area, invert_for_hole)
    outgoing = _segment_fill_outward_normal(current, next_point, area, invert_for_hole)
    if incoming is None or outgoing is None:
        return None

    normal_x = incoming[0] + outgoing[0]
    normal_y = incoming[1] + outgoing[1]
    length = hypot(normal_x, normal_y)
    if length == 0:
        return outgoing

    normal_x /= length
    normal_y /= length
    projection = normal_x * outgoing[0] + normal_y * outgoing[1]
    if abs(projection) < 0.01:
        return normal_x, normal_y

    miter_scale = max(-4.0, min(4.0, 1 / projection))
    return normal_x * miter_scale, normal_y * miter_scale


def _distinct_contour_point(
    points: list[tuple[int, int]],
    index: int,
    step: int,
) -> tuple[int, int] | None:
    current = points[index]
    for offset in range(1, len(points)):
        candidate = points[(index + step * offset) % len(points)]
        if candidate != current:
            return candidate
    return None


def _segment_fill_outward_normal(
    start: tuple[int, int],
    end: tuple[int, int],
    area: float,
    invert_for_hole: bool,
) -> tuple[float, float] | None:
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    length = hypot(dx, dy)
    if length == 0:
        return None

    if area > 0:
        normal_x = dy / length
        normal_y = -dx / length
    else:
        normal_x = -dy / length
        normal_y = dx / length

    if invert_for_hole:
        normal_x = -normal_x
        normal_y = -normal_y
    return normal_x, normal_y


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
