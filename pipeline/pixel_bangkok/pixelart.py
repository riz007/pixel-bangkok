"""Stage 5: deterministic pixel-art treatment of the procedural render.

Adds fixed texture patterns to water, grass, bare ground and flat roofs, then upscales by an
integer factor with nearest-neighbour sampling. Geometry is never moved: the
master image is the native render scaled by exactly `upscale`.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
from PIL import Image

from .config import RenderConfig
from .render import parse_color

log = logging.getLogger(__name__)


def _replace(pixels: np.ndarray, source: str, target: str, pattern: np.ndarray, palette) -> None:
    src = np.array(parse_color(palette[source])[:3], dtype=np.uint8)
    dst = np.array(parse_color(palette[target])[:3], dtype=np.uint8)
    pixels[np.all(pixels == src, axis=-1) & pattern] = dst


def apply_pixel_art(image: Image.Image, render: RenderConfig) -> Image.Image:
    pixels = np.array(image.convert("RGB"))
    height, width = pixels.shape[:2]
    ys, xs = np.mgrid[0:height, 0:width]
    ripples = (ys % 6 == 0) & ((xs + (ys // 6) * 7) % 13 < 4)
    tufts = (xs * 7 + ys * 13) % 11 == 0
    speckles = ((xs * 3 + ys * 7) % 11 == 0) & (ys % 2 == 0)
    roof_grain = ((xs + ys * 2) % 6 == 0) & (ys % 3 == 0)
    _replace(pixels, "water", "water_light", ripples, render.palette)
    _replace(pixels, "green", "green_dark", tufts, render.palette)
    _replace(pixels, "terrain", "terrain_dither", speckles, render.palette)
    _replace(pixels, "building_roof", "roof_dither", roof_grain, render.palette)
    styled = Image.fromarray(pixels, "RGB")
    return styled.resize(
        (width * render.upscale, height * render.upscale), Image.Resampling.NEAREST
    )


def unique_colors(image: Image.Image) -> int:
    pixels = np.array(image.convert("RGB")).reshape(-1, 3)
    return len(np.unique(pixels, axis=0))


def run(render: RenderConfig, build_dir: Path) -> Path:
    source = build_dir / "render.png"
    if not source.exists():
        raise FileNotFoundError(f"{source} not found; run the render stage first")
    with Image.open(source) as image:
        master = apply_pixel_art(image, render)
    output = build_dir / "master.png"
    master.save(output)
    log.info(
        "styled master %dx%d (%d colours) written to %s",
        master.width,
        master.height,
        unique_colors(master),
        output,
    )
    return output
