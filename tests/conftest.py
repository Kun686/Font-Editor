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
