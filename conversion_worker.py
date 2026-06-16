from __future__ import annotations

import json
from pathlib import Path
import sys

from font_processor import FontConversionError, write_processed_ttf


def main() -> int:
    if len(sys.argv) != 5:
        print("usage: conversion_worker.py TARGET SOURCE_OR_EMPTY OUTPUT OPTIONS_JSON", file=sys.stderr)
        return 2

    target_path = Path(sys.argv[1])
    source_path = Path(sys.argv[2]) if sys.argv[2] else None
    output_path = Path(sys.argv[3])
    options = json.loads(sys.argv[4])

    try:
        font_bytes = target_path.read_bytes()
        source_font_bytes = source_path.read_bytes() if source_path else None
        with output_path.open("wb") as output_file:
            write_processed_ttf(
                font_bytes,
                output_file,
                scale_percent=int(options["scale_percent"]),
                weight_mode=str(options["weight_mode"]),
                effect_units=options["effect_units"],
                effect_x_units=options["effect_x_units"],
                effect_y_units=options["effect_y_units"],
                spacing_left_percent=float(options["spacing_left_percent"]),
                spacing_right_percent=float(options["spacing_right_percent"]),
                spacing_top_percent=float(options["spacing_top_percent"]),
                spacing_bottom_percent=float(options["spacing_bottom_percent"]),
                source_font_bytes=source_font_bytes,
                replacement_chars=str(options["replacement_chars"]),
            )
    except FontConversionError as exc:
        print(str(exc), file=sys.stderr)
        return 3
    except Exception as exc:
        print(f"服务器转换失败: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
