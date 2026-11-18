"""Optional experiment: repaint crops of the procedural render with a local image model.

Not part of the pipeline. The procedural render stays the geometry reference;
this script only writes to build/<area>/ai-trial/ and never touches tiles.

For each window: crop the native render, upscale it (nearest), run
mflux-generate-qwen-2.1-edit, downscale the result back to the crop size and
measure drift against the render (global shift by phase correlation and
edge agreement within a pixel tolerance).
"""

from __future__ import annotations

import argparse
import json
import platform
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pixel_bangkok.config import Paths, load_area_config, load_render_config  # noqa: E402
from pixel_bangkok.crs import MapBounds  # noqa: E402
from pixel_bangkok.drift import drift  # noqa: E402
from pixel_bangkok.projection import IsoProjection  # noqa: E402

COMMAND = "mflux-generate-qwen-2.1-edit"
MODEL = "qwen-image-2.1-turbo"
LICENCE = "Qwen Research License (non-commercial research and evaluation only)"
PROMPT = (
    "Redraw this isometric city map as detailed isometric pixel art in the style of a "
    "miniature living city. Keep every building, road, river, tree and pier exactly where "
    "it is, with the same shapes, sizes and colours of roofs. Add fine pixel detail: roof "
    "textures, window frames, small street details. No text, no labels."
)
WINDOWS = {
    "wat-arun-prang": (100.48889, 13.74370),
    "tha-tien-bank": (100.49080, 13.74540),
    "west-bank-streets": (100.48770, 13.74240),
}
CROP_PX = 512


@dataclass
class Settings:
    model: str = MODEL
    steps: int = 8
    seed: int = 20261117
    strength: float = 0.7
    quantize: int = 8
    upscale: int = 2


def crop_box(area_id: str, lon: float, lat: float) -> tuple[int, int, int, int]:
    area = load_area_config(area_id)
    bounds = MapBounds.from_area(area)
    projection = IsoProjection.create(bounds, load_render_config())
    x, y = projection.world_to_native(*bounds.lonlat_to_world(lon, lat))
    left = int(round(x)) - CROP_PX // 2
    top = int(round(y)) - CROP_PX // 2
    return left, top, left + CROP_PX, top + CROP_PX


def run_model(source: Path, output: Path, settings: Settings, size: int, log: Path) -> float:
    command = [
        COMMAND,
        "--model",
        settings.model,
        "--quantize",
        str(settings.quantize),
        "--small-text-encoder",
        "--image-paths",
        str(source),
        "--prompt",
        PROMPT,
        "--steps",
        str(settings.steps),
        "--seed",
        str(settings.seed),
        "--strength",
        str(settings.strength),
        "--width",
        str(size),
        "--height",
        str(size),
        "--output",
        str(output),
    ]
    started = time.monotonic()
    with log.open("w") as handle:
        subprocess.run(command, check=True, stdout=handle, stderr=subprocess.STDOUT)
    return time.monotonic() - started


def contact_sheet(rows: list[tuple[str, Image.Image, Image.Image]], path: Path) -> None:
    cell = 512
    sheet = Image.new("RGB", (cell * 2 + 30, (cell + 30) * len(rows)), (27, 31, 42))
    draw = ImageDraw.Draw(sheet)
    for index, (name, before, after) in enumerate(rows):
        y = index * (cell + 30)
        draw.text(
            (10, y + 8), f"{name}: procedural (left) / AI repaint (right)", fill=(243, 234, 214)
        )
        sheet.paste(before.resize((cell, cell), Image.Resampling.NEAREST), (10, y + 26))
        sheet.paste(after.resize((cell, cell), Image.Resampling.LANCZOS), (cell + 20, y + 26))
    sheet.save(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--area", default="wat-arun")
    parser.add_argument("--windows", nargs="*", default=list(WINDOWS))
    parser.add_argument("--strength", type=float, default=Settings.strength)
    parser.add_argument("--steps", type=int, default=Settings.steps)
    parser.add_argument("--seed", type=int, default=Settings.seed)
    args = parser.parse_args()
    if shutil.which(COMMAND) is None:
        print(f"{COMMAND} not found; install with `uv tool install mflux`", file=sys.stderr)
        return 1
    settings = Settings(steps=args.steps, seed=args.seed, strength=args.strength)
    paths = Paths.for_area(args.area)
    render_path = paths.build_dir / "render.png"
    if not render_path.exists():
        print(f"{render_path} missing; run the render stage first", file=sys.stderr)
        return 1
    out_dir = paths.build_dir / "ai-trial" / f"s{settings.strength:g}-seed{settings.seed}"
    out_dir.mkdir(parents=True, exist_ok=True)
    render = Image.open(render_path).convert("RGB")
    size = CROP_PX * settings.upscale
    results = []
    rows = []
    for name in args.windows:
        lon, lat = WINDOWS[name]
        box = crop_box(args.area, lon, lat)
        crop = render.crop(box)
        source = out_dir / f"{name}.input.png"
        crop.resize((size, size), Image.Resampling.NEAREST).save(source)
        output = out_dir / f"{name}.ai.png"
        seconds = run_model(source, output, settings, size, out_dir / f"{name}.log")
        repainted = Image.open(output).convert("RGB")
        back = repainted.resize(crop.size, Image.Resampling.LANCZOS)
        metrics = drift(crop, back)
        baseline = drift(crop, crop)
        results.append(
            {
                "window": name,
                "crop_box_native_px": box,
                "seconds": round(seconds, 1),
                **metrics,
                "self_check": baseline,
            }
        )
        rows.append((name, crop, repainted))
        print(json.dumps(results[-1]), flush=True)
    contact_sheet(rows, out_dir / "comparison.png")
    record = {
        "command": COMMAND,
        "model": settings.model,
        "licence": LICENCE,
        "prompt": PROMPT,
        "settings": asdict(settings),
        "crop_px": CROP_PX,
        "gate": "pixel_bangkok.drift",
        "machine": platform.machine(),
        "platform": platform.platform(),
        "results": results,
        "cost": "local inference; no API charges",
    }
    (out_dir / "trial.json").write_text(json.dumps(record, indent=2))
    print(f"wrote {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
