from io import BytesIO

import pytest
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen


def _glyph_square():
    pen = TTGlyphPen(None)
    pen.moveTo((50, 0))
    pen.lineTo((450, 0))
    pen.lineTo((450, 500))
    pen.lineTo((50, 500))
    pen.closePath()
    return pen.glyph()


def _glyph_rectangle(bounds):
    x_min, y_min, x_max, y_max = bounds
    pen = TTGlyphPen(None)
    pen.moveTo((x_min, y_min))
    pen.lineTo((x_max, y_min))
    pen.lineTo((x_max, y_max))
    pen.lineTo((x_min, y_max))
    pen.closePath()
    return pen.glyph()


def _build_ttf_bytes(
    glyph_bounds_by_char: dict[str, tuple[int, int, int, int]],
    *,
    units_per_em: int = 1000,
) -> bytes:
    glyph_order = [".notdef", *[f"glyph{ord(char):04X}" for char in glyph_bounds_by_char]]
    builder = FontBuilder(units_per_em, isTTF=True)
    builder.setupGlyphOrder(glyph_order)
    builder.setupCharacterMap({ord(char): f"glyph{ord(char):04X}" for char in glyph_bounds_by_char})
    builder.setupGlyf(
        {
            ".notdef": TTGlyphPen(None).glyph(),
            **{
                f"glyph{ord(char):04X}": _glyph_rectangle(bounds)
                for char, bounds in glyph_bounds_by_char.items()
            },
        }
    )
    builder.setupHorizontalMetrics(
        {
            ".notdef": (units_per_em // 2, 0),
            **{
                f"glyph{ord(char):04X}": (bounds[2] + 50, bounds[0])
                for char, bounds in glyph_bounds_by_char.items()
            },
        }
    )
    builder.setupHorizontalHeader(ascent=int(units_per_em * 0.8), descent=-int(units_per_em * 0.2))
    builder.setupNameTable(
        {
            "familyName": "GeneratedTestFont",
            "styleName": "Regular",
            "uniqueFontIdentifier": "GeneratedTestFont Regular",
            "fullName": "GeneratedTestFont Regular",
            "psName": "GeneratedTestFont-Regular",
        }
    )
    builder.setupOS2(
        sTypoAscender=int(units_per_em * 0.8),
        sTypoDescender=-int(units_per_em * 0.2),
        usWinAscent=int(units_per_em * 0.8),
        usWinDescent=int(units_per_em * 0.2),
    )
    builder.setupPost()

    buffer = BytesIO()
    builder.save(buffer)
    return buffer.getvalue()


@pytest.fixture
def build_ttf_bytes():
    return _build_ttf_bytes


@pytest.fixture
def sample_ttf_bytes():
    units_per_em = 1000
    glyph_order = [".notdef", "A"]
    builder = FontBuilder(units_per_em, isTTF=True)
    builder.setupGlyphOrder(glyph_order)
    builder.setupCharacterMap({65: "A"})
    builder.setupGlyf({".notdef": TTGlyphPen(None).glyph(), "A": _glyph_square()})
    builder.setupHorizontalMetrics({".notdef": (500, 0), "A": (500, 50)})
    builder.setupHorizontalHeader(ascent=800, descent=-200)
    builder.setupNameTable(
        {
            "familyName": "TestFont",
            "styleName": "Regular",
            "uniqueFontIdentifier": "TestFont Regular",
            "fullName": "TestFont Regular",
            "psName": "TestFont-Regular",
        }
    )
    builder.setupOS2(
        sTypoAscender=800,
        sTypoDescender=-200,
        usWinAscent=800,
        usWinDescent=200,
    )
    builder.setupPost()

    buffer = BytesIO()
    builder.save(buffer)
    return buffer.getvalue()
