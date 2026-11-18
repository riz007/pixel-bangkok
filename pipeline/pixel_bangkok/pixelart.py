"""Stage 5: deterministic pixel-art treatment of the procedural render.

Adds fixed texture patterns to water, grass, bare ground and flat roofs, then upscales by an
integer factor with nearest-neighbour sampling. Geometry is never moved: the
master image is the native render scaled by exactly `upscale`.

Near the area rectangle's edge the map dissolves into the background with an ordered
dither, so coverage ends in a soft, ragged fade instead of a hard box. The ragged line is
presentation only (value noise in world metres); it never adds or moves features.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
from PIL import Image

from .config import AreaConfig, RenderConfig
from .crs import MapBounds
from .projection import IsoProjection
from .render import parse_color

log = logging.getLogger(__name__)

ROOF_GRAIN_FACTOR = 0.95
EDGE_FADE_MAX_M = 900.0
EDGE_FADE_FRACTION = 0.03
EDGE_NOISE_MIN_CELLS_M = (260.0, 90.0)
EDGE_NOISE_CELL_BANDS = (3.0, 1.0)
EDGE_NOISE_WEIGHTS = (1.0, 0.3)
EDGE_CORNER_BANDS = 4.0
BAYER_8 = (
    np.array(
        [
            [0, 32, 8, 40, 2, 34, 10, 42],
            [48, 16, 56, 24, 50, 18, 58, 26],
            [12, 44, 4, 36, 14, 46, 6, 38],
            [60, 28, 52, 20, 62, 30, 54, 22],
            [3, 35, 11, 43, 1, 33, 9, 41],
            [51, 19, 59, 27, 49, 17, 57, 25],
            [15, 47, 7, 39, 13, 45, 5, 37],
            [63, 31, 55, 23, 61, 29, 53, 21],
        ]
    )
    + 0.5
) / 64


def _lattice(ix: np.ndarray, iy: np.ndarray, seed: int) -> np.ndarray:
    h = (ix.astype(np.int64) * 73856093) ^ (iy.astype(np.int64) * 19349663) ^ seed
    h = (h ^ (h >> 13)) * 1274126177
    return ((h ^ (h >> 16)) & 0xFFFF) / 65535.0


def _value_noise(x: np.ndarray, y: np.ndarray, cell: float, seed: int) -> np.ndarray:
    gx, gy = x / cell, y / cell
    ix, iy = np.floor(gx), np.floor(gy)
    fx, fy = gx - ix, gy - iy
    sx, sy = fx * fx * (3 - 2 * fx), fy * fy * (3 - 2 * fy)
    a = _lattice(ix, iy, seed)
    b = _lattice(ix + 1, iy, seed)
    c = _lattice(ix, iy + 1, seed)
    d = _lattice(ix + 1, iy + 1, seed)
    return (a + (b - a) * sx) + ((c + (d - c) * sx) - (a + (b - a) * sx)) * sy


def edge_dissolve(
    bounds: MapBounds, render: RenderConfig, box: tuple[int, int, int, int]
) -> np.ndarray:
    """Native pixels in `box` (left, top, right, bottom) that dissolve into the background."""
    projection = IsoProjection.create(bounds, render)
    left, top, right, bottom = box
    ys, xs = np.mgrid[top:bottom, left:right].astype(np.float64)
    determinant = projection.ax * projection.by - projection.ay * projection.bx
    dx, dy = xs - projection.tx, ys - projection.ty
    wx = (projection.by * dx - projection.ay * dy) / determinant
    wy = (projection.ax * dy - projection.bx * dx) / determinant
    band = min(EDGE_FADE_MAX_M, EDGE_FADE_FRACTION * min(bounds.width_m, bounds.height_m))
    radius = EDGE_CORNER_BANDS * band
    qx = np.maximum.reduce([radius - wx, np.zeros_like(wx), wx - (bounds.width_m - radius)])
    qy = np.maximum.reduce([radius - wy, np.zeros_like(wy), wy - (bounds.height_m - radius)])
    outside = np.hypot(qx, qy)
    inside = np.minimum.reduce(
        [wx - radius, bounds.width_m - radius - wx, wy - radius, bounds.height_m - radius - wy]
    )
    inset = np.where(outside > 0, radius - outside, radius + np.maximum(inside, 0))
    level = inset / band - sum(EDGE_NOISE_WEIGHTS)
    cells = [
        max(minimum, band * factor)
        for minimum, factor in zip(EDGE_NOISE_MIN_CELLS_M, EDGE_NOISE_CELL_BANDS, strict=True)
    ]
    for index, (cell, weight) in enumerate(zip(cells, EDGE_NOISE_WEIGHTS, strict=True)):
        level += (_value_noise(wx, wy, cell, render.seed + index) - 0.5) * 2 * weight
    threshold = BAYER_8[ys.astype(np.int64) % 8, xs.astype(np.int64) % 8]
    return level < threshold


def _replace(
    pixels: np.ndarray, source: str, target: str, pattern: np.ndarray, palette: dict | None
) -> None:
    """Swap `source` pixels to `target` where `pattern` is set (palette names or hex colours)."""
    src = np.array(parse_color(palette[source] if palette else source)[:3], dtype=np.uint8)
    dst = np.array(parse_color(palette[target] if palette else target)[:3], dtype=np.uint8)
    pixels[np.all(pixels == src, axis=-1) & pattern] = dst


def apply_pixel_art(
    image: Image.Image, render: RenderConfig, origin: tuple[int, int] = (0, 0)
) -> Image.Image:
    """Texture patterns use global native coordinates so blocks line up seamlessly."""
    pixels = np.array(image.convert("RGB"))
    height, width = pixels.shape[:2]
    ys, xs = np.mgrid[origin[1] : origin[1] + height, origin[0] : origin[0] + width].astype(
        np.int32
    )
    ripples = (ys % 6 == 0) & ((xs + (ys // 6) * 7) % 13 < 4)
    tufts = (xs * 7 + ys * 13) % 11 == 0
    speckles = ((xs * 3 + ys * 7) % 11 == 0) & (ys % 2 == 0)
    roof_grain = ((xs + ys * 2) % 6 == 0) & (ys % 3 == 0)
    _replace(pixels, "water", "water_light", ripples, render.palette)
    _replace(pixels, "green", "green_dark", tufts, render.palette)
    _replace(pixels, "terrain", "terrain_dither", speckles, render.palette)
    _replace(pixels, "building_roof", "roof_dither", roof_grain, render.palette)
    for material, colours in render.materials.items():
        if colours.get("roof_texture") == "metal" or material.startswith("rooftop_"):
            continue
        roof = parse_color(colours["roof"])
        grain = "#{:02x}{:02x}{:02x}".format(*(int(c * ROOF_GRAIN_FACTOR) for c in roof[:3]))
        _replace(pixels, colours["roof"], grain, roof_grain, None)
    styled = Image.fromarray(pixels, "RGB")
    return styled.resize(
        (width * render.upscale, height * render.upscale), Image.Resampling.NEAREST
    )


def overlay_from_mask(master: Image.Image, mask: np.ndarray) -> Image.Image:
    """Master pixels covered by buildings or trees, transparent elsewhere.

    The viewer draws this above animated vehicles so they pass behind buildings.
    """
    scale = master.width // mask.shape[1]
    if scale > 1:
        mask = mask.repeat(scale, axis=0).repeat(scale, axis=1)
    alpha = np.where(mask, 255, 0).astype(np.uint8)
    return Image.fromarray(np.dstack([np.asarray(master.convert("RGB")), alpha]), "RGBA")


def unique_colors(image: Image.Image) -> int:
    pixels = np.array(image.convert("RGB")).reshape(-1, 3)
    return len(np.unique(pixels, axis=0))


def faded(image: Image.Image, dissolve: np.ndarray, render: RenderConfig) -> Image.Image:
    """Replace dissolved pixels with the background colour (upscaled to the image size)."""
    scale = image.width // dissolve.shape[1]
    if scale > 1:
        dissolve = dissolve.repeat(scale, axis=0).repeat(scale, axis=1)
    pixels = np.array(image.convert("RGB"))
    pixels[dissolve] = parse_color(render.palette["background"])[:3]
    return Image.fromarray(pixels, "RGB")


def run(render: RenderConfig, build_dir: Path, area: AreaConfig | None = None) -> Path:
    from .blocks import blocks_of, read_info

    blocks_dir = build_dir / "blocks"
    info = read_info(blocks_dir)
    bounds = MapBounds.from_area(area) if area is not None else None
    for block in blocks_of(info):
        with Image.open(blocks_dir / f"render_{block.name}.png") as image:
            master = apply_pixel_art(image, render, (block.left, block.top))
        box = (block.left, block.top, block.left + block.width, block.top + block.height)
        dissolve = (
            edge_dissolve(bounds, render, box)
            if bounds is not None
            else np.zeros((block.height, block.width), dtype=bool)
        )
        master = faded(master, dissolve, render)
        master.save(blocks_dir / f"master_{block.name}.png")
        with Image.open(blocks_dir / f"occlusion_{block.name}.png") as occlusion:
            mask = np.asarray(occlusion.convert("1")) | dissolve
        overlay_from_mask(master, mask).save(blocks_dir / f"overlay_{block.name}.png")
        front_path = blocks_dir / f"front_{block.name}.png"
        if front_path.exists():
            with Image.open(front_path) as front:
                front_mask = np.asarray(front.convert("1")) | dissolve
            overlay_from_mask(master, front_mask).save(
                blocks_dir / f"front_overlay_{block.name}.png"
            )
    log.info("styled %d blocks in %s", len(info["blocks"]), blocks_dir)
    return blocks_dir
