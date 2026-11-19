"""Stitch one published pyramid level of an area into a PNG (for the OG card).

    uv run --project pipeline python pipeline/experiments/og_source.py bangkok 1800 out.png
Picks the smallest level at least `min_width` pixels wide; blank tiles show the background.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image

from pixel_bangkok.config import load_render_config
from pixel_bangkok.render import parse_color


def main() -> int:
    area, min_width, output = sys.argv[1], int(sys.argv[2]), Path(sys.argv[3])
    root = Path("apps/web/public/maps") / area
    manifest = json.loads((root / "manifest.json").read_text())
    tiles = manifest["tiles"]
    level = next(e for e in tiles["levels"] if e["width"] >= min_width)
    size, overlap = tiles["tile_size"], tiles["overlap"]
    background = parse_color(load_render_config().palette["background"])[:3]
    image = Image.new("RGB", (level["width"], level["height"]), background)
    for row in range(level["rows"]):
        for column in range(level["columns"]):
            path = root / "tiles" / str(level["level"]) / f"{column}_{row}.{tiles['format']}"
            if not path.exists():
                continue
            with Image.open(path) as tile:
                left = 0 if column == 0 else overlap
                top = 0 if row == 0 else overlap
                image.paste(
                    tile.convert("RGB").crop((left, top, left + size, top + size)),
                    (column * size, row * size),
                )
    image.save(output)
    print(output, image.size)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
