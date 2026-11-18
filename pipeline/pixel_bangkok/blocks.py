"""Block-wise rendering for areas whose image is too large to hold in memory.

The native image is divided into square blocks aligned to the tile grid. Each
block is drawn with the area projection shifted to the block's origin, using
only features that can reach the block on screen. Results are pixel-identical
to rendering the whole image at once, apart from depth-cycle tie-breaks.

Files in build/<area>/blocks/:
- render_<bx>_<by>.png: composited procedural render (RGB).
- occlusion_<bx>_<by>.png: 1-bit mask of building, tree and viaduct pixels.
- front_<bx>_<by>.png: 1-bit mask of building and tree pixels in front of a viaduct.
- master_<bx>_<by>.png, overlay_<bx>_<by>.png: written by the style stage.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import math
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image
from shapely import STRtree
from shapely.geometry import Polygon
from shapely.geometry.base import BaseGeometry

from .config import RenderConfig
from .crs import MapBounds
from .projection import IsoProjection

log = logging.getLogger(__name__)

BLOCK_PX = 4096
SCREEN_MARGIN_PX = 16
Feature = tuple[BaseGeometry, dict]


@dataclass(frozen=True)
class Block:
    column: int
    row: int
    left: int
    top: int
    width: int
    height: int

    @property
    def name(self) -> str:
        return f"{self.column}_{self.row}"


def block_grid(width: int, height: int, block_px: int = BLOCK_PX) -> list[Block]:
    return [
        Block(
            column,
            row,
            column * block_px,
            row * block_px,
            min(block_px, width - column * block_px),
            min(block_px, height - row * block_px),
        )
        for row in range(math.ceil(height / block_px))
        for column in range(math.ceil(width / block_px))
    ]


def shifted(projection: IsoProjection, block: Block) -> IsoProjection:
    return dataclasses.replace(
        projection,
        tx=projection.tx - block.left,
        ty=projection.ty - block.top,
        native_width=block.width,
        native_height=block.height,
    )


def screen_to_ground(projection: IsoProjection, px: float, py: float) -> tuple[float, float]:
    """Native pixel -> world metres on the ground plane (z = 0)."""
    determinant = projection.ax * projection.by - projection.ay * projection.bx
    dx, dy = px - projection.tx, py - projection.ty
    return (
        (projection.by * dx - projection.ay * dy) / determinant,
        (projection.ax * dy - projection.bx * dx) / determinant,
    )


def ground_window(projection: IsoProjection, block: Block, render: RenderConfig) -> Polygon:
    """World-space region whose features can draw into the block."""
    rise_px = math.ceil(-projection.bz * render.max_height_m)
    left = block.left - SCREEN_MARGIN_PX
    right = block.left + block.width + SCREEN_MARGIN_PX
    top = block.top - SCREEN_MARGIN_PX
    bottom = block.top + block.height + rise_px + SCREEN_MARGIN_PX
    corners = [
        screen_to_ground(projection, x, y)
        for x, y in ((left, top), (right, top), (right, bottom), (left, bottom))
    ]
    shadow_m = render.max_height_m * render.shadow_length_per_metre
    return Polygon(corners).buffer(shadow_m + render.trees.max_crown_radius_m)


class FeatureIndex:
    def __init__(self, layers: dict[str, list[Feature]]) -> None:
        self.layers = layers
        self.trees = {
            name: STRtree([geometry for geometry, _ in features])
            for name, features in layers.items()
            if features
        }

    def select(self, window: BaseGeometry) -> dict[str, list[Feature]]:
        selected: dict[str, list[Feature]] = {}
        for name, features in self.layers.items():
            tree = self.trees.get(name)
            if tree is None:
                selected[name] = []
                continue
            hits = sorted(int(i) for i in tree.query(window, predicate="intersects"))
            selected[name] = [features[i] for i in hits]
        return selected


def render_blocks(
    bounds: MapBounds,
    render: RenderConfig,
    layers: dict[str, list[Feature]],
    blocks_dir: Path,
    block_px: int = BLOCK_PX,
    inputs_key: str | None = None,
) -> dict[str, object]:
    """Render every block; with `inputs_key`, blocks finished by an earlier run with the same key
    are kept, so an interrupted render resumes."""
    from .render import composite, parse_color, render_layers

    projection = IsoProjection.create(bounds, render)
    blocks = block_grid(projection.native_width, projection.native_height, block_px)
    blocks_dir.mkdir(parents=True, exist_ok=True)
    key_path = blocks_dir / "render-key.json"
    resume = (
        inputs_key is not None
        and key_path.exists()
        and json.loads(key_path.read_text(encoding="utf-8")).get("key") == inputs_key
    )
    if not resume:
        for stale in blocks_dir.glob("*.png"):
            stale.unlink()
        (blocks_dir / "blocks.json").unlink(missing_ok=True)
        if inputs_key is not None:
            key_path.write_text(json.dumps({"key": inputs_key}), encoding="utf-8")
    index = FeatureIndex(layers)
    background = parse_color(render.palette["background"])
    started = time.monotonic()
    for number, block in enumerate(blocks, start=1):
        outputs = [
            blocks_dir / f"{kind}_{block.name}.png" for kind in ("render", "occlusion", "front")
        ]
        if resume and all(path.exists() for path in outputs):
            continue
        selected = index.select(ground_window(projection, block, render))
        drawn = render_layers(bounds, render, selected, projection=shifted(projection, block))
        occlusion = np.asarray(drawn["buildings"])[..., 3] > 0
        occlusion |= np.asarray(drawn["vegetation"])[..., 3] > 0
        Image.fromarray(occlusion).save(blocks_dir / f"occlusion_{block.name}.png")
        front = np.asarray(drawn["front"])[..., 3] > 0
        Image.fromarray(front).save(blocks_dir / f"front_{block.name}.png")
        partial = blocks_dir / f"render_{block.name}.partial.png"
        composite(drawn, background).save(partial)
        partial.replace(blocks_dir / f"render_{block.name}.png")
        log.info(
            "block %s (%d/%d): %d buildings, %d trees, %.0fs elapsed",
            block.name,
            number,
            len(blocks),
            len(selected.get("buildings", [])),
            len(selected.get("trees", [])),
            time.monotonic() - started,
        )
    info = {
        "width": projection.native_width,
        "height": projection.native_height,
        "block_px": block_px,
        "blocks": [dataclasses.asdict(block) for block in blocks],
    }
    (blocks_dir / "blocks.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
    return info


def read_info(blocks_dir: Path) -> dict:
    path = blocks_dir / "blocks.json"
    if not path.exists():
        raise FileNotFoundError(f"{path} not found; run the render stage first")
    return json.loads(path.read_text(encoding="utf-8"))


def blocks_of(info: dict) -> list[Block]:
    return [Block(**entry) for entry in info["blocks"]]


def read_region(
    blocks_dir: Path, prefix: str, box: tuple[int, int, int, int], mode: str
) -> Image.Image:
    """Assemble an arbitrary native-pixel region from block files."""
    info = read_info(blocks_dir)
    left, top, right, bottom = box
    region = Image.new(mode, (right - left, bottom - top))
    for block in blocks_of(info):
        overlap_left = max(left, block.left)
        overlap_top = max(top, block.top)
        overlap_right = min(right, block.left + block.width)
        overlap_bottom = min(bottom, block.top + block.height)
        if overlap_left >= overlap_right or overlap_top >= overlap_bottom:
            continue
        with Image.open(blocks_dir / f"{prefix}_{block.name}.png") as image:
            piece = image.convert(mode).crop(
                (
                    overlap_left - block.left,
                    overlap_top - block.top,
                    overlap_right - block.left,
                    overlap_bottom - block.top,
                )
            )
        region.paste(piece, (overlap_left - left, overlap_top - top))
    return region
