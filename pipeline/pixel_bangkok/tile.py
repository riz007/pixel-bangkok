"""Stage 6: Deep Zoom tile pyramid and manifest.

Layout matches the Deep Zoom convention: level N has the full image at
max_level, halving each level down to 1 px. Tiles are stored as
tiles/<level>/<column>_<row>.<format>; neighbouring tiles share `overlap`
pixels on interior edges.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import shutil
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from .config import AreaConfig, RenderConfig, TileConfig
from .crs import MapBounds
from .projection import IsoProjection

log = logging.getLogger(__name__)

MANIFEST_VERSION = 3
Image.MAX_IMAGE_PIXELS = None


def level_dimensions(width: int, height: int) -> list[dict[str, int]]:
    max_level = math.ceil(math.log2(max(width, height)))
    levels = []
    for level in range(max_level + 1):
        scale = 2 ** (max_level - level)
        levels.append(
            {"level": level, "width": math.ceil(width / scale), "height": math.ceil(height / scale)}
        )
    return levels


def tile_box(
    column: int, row: int, width: int, height: int, tile_size: int, overlap: int
) -> tuple[int, int, int, int]:
    left = max(column * tile_size - overlap, 0)
    top = max(row * tile_size - overlap, 0)
    right = min((column + 1) * tile_size + overlap, width)
    bottom = min((row + 1) * tile_size + overlap, height)
    return left, top, right, bottom


def _pack(image: Image.Image) -> np.ndarray:
    rgba = np.asarray(image.convert("RGBA"), dtype=np.uint8)
    return rgba.view(np.uint32)[..., 0]


def _unpack(packed: np.ndarray, mode: str) -> Image.Image:
    rgba = packed[..., None].view(np.uint8).reshape(*packed.shape, 4)
    return Image.fromarray(np.ascontiguousarray(rgba), "RGBA").convert(mode)


def box_pool(packed: np.ndarray) -> np.ndarray:
    """Halve an image by averaging each 2x2 block, alpha-weighted so transparent pixels add no
    colour. Overview levels then look like a smaller view of the map rather than aliased
    noise; the full-resolution level keeps every pixel. Odd edges repeat the last row/column.
    """
    height, width = packed.shape
    padded = np.pad(packed, ((0, height % 2), (0, width % 2)), mode="edge")
    rgba = padded[..., None].view(np.uint8).reshape(*padded.shape, 4).astype(np.float64)
    quads = rgba.reshape(padded.shape[0] // 2, 2, padded.shape[1] // 2, 2, 4)
    alpha = quads[..., 3:4]
    weight = alpha.sum(axis=(1, 3))
    colour = (quads[..., :3] * alpha).sum(axis=(1, 3)) / np.maximum(weight, 1e-9)
    out = np.concatenate([colour, weight / 4], axis=-1)
    out = np.where(weight > 0, out, 0).round().clip(0, 255).astype(np.uint8)
    return np.ascontiguousarray(out).view(np.uint32)[..., 0]


def level_images(master: Image.Image, levels: list[dict[str, int]]):
    """Yield (level entry, image) from the full-resolution level downwards."""
    packed = _pack(master)
    for entry in reversed(levels):
        assert packed.shape == (entry["height"], entry["width"])
        yield entry, _unpack(packed, master.mode)
        if packed.shape != (1, 1):
            packed = box_pool(packed)


def _core_path(work_dir: Path, level: int, column: int, row: int) -> Path:
    return work_dir / str(level) / f"{column}_{row}.png"


def _save_core(work_dir: Path, level: int, column: int, row: int, packed: np.ndarray) -> None:
    path = _core_path(work_dir, level, column, row)
    path.parent.mkdir(parents=True, exist_ok=True)
    _unpack(packed, "RGBA").save(path, compress_level=1)


def _load_core(work_dir: Path, level: int, column: int, row: int) -> np.ndarray | None:
    path = _core_path(work_dir, level, column, row)
    if not path.exists():
        return None
    with Image.open(path) as image:
        return _pack(image)


def write_pyramid_blocks(
    blocks: list[tuple[tuple[int, int], Callable[[], Image.Image]]],
    width: int,
    height: int,
    mode: str,
    tiles_dir: Path,
    tiles: TileConfig,
    work_dir: Path,
) -> list[dict[str, int]]:
    """Deep Zoom pyramid built from image blocks without holding the whole image.

    `blocks` maps each block's top-left corner (multiples of the tile size) to a
    loader. Lower levels are 2x2 averages of the level above, tile by tile, so
    the result equals pooling the whole image at once.
    """
    size = tiles.tile_size
    if tiles_dir.exists():
        shutil.rmtree(tiles_dir)
    if work_dir.exists():
        shutil.rmtree(work_dir)
    levels = level_dimensions(width, height)
    top = levels[-1]
    for (left, top_px), load in blocks:
        if left % size or top_px % size:
            raise ValueError("block origins must be multiples of the tile size")
        packed = _pack(load())
        for y in range(0, packed.shape[0], size):
            for x in range(0, packed.shape[1], size):
                _save_core(
                    work_dir,
                    top["level"],
                    (left + x) // size,
                    (top_px + y) // size,
                    packed[y : y + size, x : x + size],
                )
    for entry in reversed(levels[:-1]):
        child_level = entry["level"] + 1
        for row in range(math.ceil(entry["height"] / size)):
            for column in range(math.ceil(entry["width"] / size)):
                children = [
                    [
                        _load_core(work_dir, child_level, 2 * column + dx, 2 * row + dy)
                        for dx in (0, 1)
                    ]
                    for dy in (0, 1)
                ]
                rows = [
                    np.hstack([child for child in pair if child is not None])
                    for pair in children
                    if pair[0] is not None
                ]
                _save_core(work_dir, entry["level"], column, row, box_pool(np.vstack(rows)))

    save_options: dict[str, Any] = {"lossless": tiles.lossless} if tiles.format == "webp" else {}
    for entry in levels:
        entry["columns"] = math.ceil(entry["width"] / size)
        entry["rows"] = math.ceil(entry["height"] / size)
        level_dir = tiles_dir / str(entry["level"])
        level_dir.mkdir(parents=True)
        cache: dict[tuple[int, int], np.ndarray | None] = {}

        def core(
            column: int,
            row: int,
            level: int = entry["level"],
            cache: dict[tuple[int, int], np.ndarray | None] = cache,
        ) -> np.ndarray | None:
            key = (column, row)
            if key not in cache:
                cache[key] = _load_core(work_dir, level, column, row)
            return cache[key]

        for row in range(entry["rows"]):
            for key in [k for k in cache if k[1] < row - 1]:
                del cache[key]
            for column in range(entry["columns"]):
                left, upper, right, lower = tile_box(
                    column, row, entry["width"], entry["height"], size, tiles.overlap
                )
                region = np.zeros((lower - upper, right - left), dtype=np.uint32)
                for neighbour_row in range(upper // size, (lower - 1) // size + 1):
                    for neighbour_column in range(left // size, (right - 1) // size + 1):
                        piece = core(neighbour_column, neighbour_row)
                        if piece is None:
                            continue
                        x0, y0 = neighbour_column * size, neighbour_row * size
                        sx0, sy0 = max(left, x0), max(upper, y0)
                        sx1 = min(right, x0 + piece.shape[1])
                        sy1 = min(lower, y0 + piece.shape[0])
                        region[sy0 - upper : sy1 - upper, sx0 - left : sx1 - left] = piece[
                            sy0 - y0 : sy1 - y0, sx0 - x0 : sx1 - x0
                        ]
                _unpack(region, mode).save(
                    level_dir / f"{column}_{row}.{tiles.format}", **save_options
                )
    shutil.rmtree(work_dir)
    return levels


def write_pyramid(master: Image.Image, tiles_dir: Path, tiles: TileConfig) -> list[dict[str, int]]:
    return write_pyramid_blocks(
        [((0, 0), lambda: master)],
        master.width,
        master.height,
        master.mode,
        tiles_dir,
        tiles,
        tiles_dir.parent / f".{tiles_dir.name}-work",
    )


def attributions(area: AreaConfig, raster_sources_used: tuple[str, ...]) -> list[dict[str, str]]:
    entries = [
        {
            "text": area.source.attribution,
            "url": area.source.attribution_url,
            "licence": area.source.licence,
            "provider": area.source.provider,
        }
    ]
    configured = {"building_heights": area.building_heights, "tree_canopy": area.tree_canopy}
    for key in raster_sources_used:
        if key == "wikidata":
            entries.append(
                {
                    "text": "Landmark descriptions: Wikidata",
                    "url": "https://www.wikidata.org/wiki/Wikidata:Licensing",
                    "licence": "CC0 1.0",
                    "provider": "Wikidata",
                }
            )
            continue
        source = configured.get(key)
        if source is not None:
            entries.append(
                {
                    "text": source.attribution,
                    "url": source.url,
                    "licence": source.licence,
                    "provider": source.dataset,
                }
            )
    return entries


def build_manifest(
    area: AreaConfig,
    render: RenderConfig,
    master_size: tuple[int, int],
    levels: list[dict[str, int]],
    master_sha256: str,
    source_metadata: dict[str, Any],
    raster_sources_used: tuple[str, ...] = (),
) -> dict[str, Any]:
    bounds = MapBounds.from_area(area)
    projection = IsoProjection.create(bounds, render)
    if master_size != (projection.master_width, projection.master_height):
        raise ValueError(
            f"master image is {master_size}, but the render config implies "
            f"{(projection.master_width, projection.master_height)}; re-run render and style"
        )
    return {
        "version": MANIFEST_VERSION,
        "area_id": area.id,
        "name": {"en": area.name_en, "th": area.name_th},
        "image": {"width": master_size[0], "height": master_size[1]},
        "tiles": {
            "tile_size": render.tiles.tile_size,
            "overlap": render.tiles.overlap,
            "format": render.tiles.format,
            "url_template": "tiles/{level}/{column}_{row}.{format}",
            "min_level": levels[0]["level"],
            "max_level": levels[-1]["level"],
            "levels": levels,
        },
        "projection": {
            "description": (
                "image_px = px[0]*x + px[1]*y + px[2]*z + px[3]; "
                "image_py = py[0]*x + py[1]*y + py[2]*z + py[3]; "
                "x east, y north, z up in metres from the bounds origin in `crs`"
            ),
            "bounds": bounds.to_dict(),
            "camera": {
                "azimuth_deg": render.camera_azimuth_deg,
                "elevation_deg": render.camera_elevation_deg,
            },
            "pixels_per_metre": render.pixels_per_metre,
            "upscale": render.upscale,
            "world_to_image": projection.master_matrix(),
        },
        "attributions": attributions(area, raster_sources_used),
        "source": {
            "dataset": area.source.dataset,
            "retrieved_at": source_metadata.get("retrieved_at"),
            "osm_base_timestamp": source_metadata.get("osm_base_timestamp"),
        },
        "generated": {
            "at": datetime.now(UTC).isoformat(timespec="seconds"),
            "master_sha256": master_sha256,
        },
    }


def _existing_levels(width: int, height: int, tile_size: int) -> list[dict[str, int]]:
    levels = level_dimensions(width, height)
    for entry in levels:
        entry["columns"] = math.ceil(entry["width"] / tile_size)
        entry["rows"] = math.ceil(entry["height"] / tile_size)
    return levels


PYRAMID_DIRS = {
    "tiles": "tiles",
    "overlay": "overlay",
    "front_overlay": "front",
    "ai_tiles": "ai",
    "ai_overlay_tiles": "ai_overlay",
    "ai_front_overlay_tiles": "ai_front",
}
"""Build directory name -> published directory name for every tile pyramid."""


def run(
    area: AreaConfig,
    render: RenderConfig,
    raw_dir: Path,
    processed_dir: Path,
    build_dir: Path,
    ai_only: bool = False,
) -> Path:
    """Write tile pyramids and the manifest; `ai_only` reuses existing base and overlay tiles."""
    from .blocks import blocks_of, read_info

    blocks_dir = build_dir / "blocks"
    info = read_info(blocks_dir)
    blocks = blocks_of(info)
    scale = render.upscale
    width, height = info["width"] * scale, info["height"] * scale
    metadata_path = processed_dir / "metadata.json"
    source_metadata = (
        json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.exists() else {}
    )

    def loaders(prefix: str, mode: str):
        return [
            (
                (block.left * scale, block.top * scale),
                lambda name=block.name: Image.open(blocks_dir / f"{prefix}_{name}.png").convert(
                    mode
                ),
            )
            for block in blocks
        ]

    has_overlay = all((blocks_dir / f"overlay_{block.name}.png").exists() for block in blocks)
    reuse = ai_only and (build_dir / "tiles").exists()
    if reuse:
        levels = _existing_levels(width, height, render.tiles.tile_size)
    else:
        levels = write_pyramid_blocks(
            loaders("master", "RGB"),
            width,
            height,
            "RGB",
            build_dir / "tiles",
            render.tiles,
            build_dir / ".tiles-work",
        )
    if has_overlay and reuse:
        has_overlay = (build_dir / "overlay").exists()
    elif has_overlay:
        write_pyramid_blocks(
            loaders("overlay", "RGBA"),
            width,
            height,
            "RGBA",
            build_dir / "overlay",
            render.tiles,
            build_dir / ".overlay-work",
        )
    elif (build_dir / "overlay").exists():
        shutil.rmtree(build_dir / "overlay")
    has_front = all((blocks_dir / f"front_overlay_{block.name}.png").exists() for block in blocks)
    if has_front and reuse:
        has_front = (build_dir / "front_overlay").exists()
    elif has_front:
        write_pyramid_blocks(
            loaders("front_overlay", "RGBA"),
            width,
            height,
            "RGBA",
            build_dir / "front_overlay",
            render.tiles,
            build_dir / ".front-work",
        )
    elif (build_dir / "front_overlay").exists():
        shutil.rmtree(build_dir / "front_overlay")
    has_ai = all((blocks_dir / f"ai_master_{block.name}.png").exists() for block in blocks)
    has_ai_front = has_ai and all(
        (blocks_dir / f"ai_front_overlay_{block.name}.png").exists() for block in blocks
    )
    for prefix, mode, directory, wanted in (
        ("ai_master", "RGB", "ai_tiles", has_ai),
        ("ai_overlay", "RGBA", "ai_overlay_tiles", has_ai),
        ("ai_front_overlay", "RGBA", "ai_front_overlay_tiles", has_ai_front),
    ):
        if wanted:
            write_pyramid_blocks(
                loaders(prefix, mode),
                width,
                height,
                mode,
                build_dir / directory,
                render.tiles,
                build_dir / f".{directory}-work",
            )
        elif (build_dir / directory).exists():
            shutil.rmtree(build_dir / directory)
    digest = hashlib.sha256()
    for block in blocks:
        digest.update((blocks_dir / f"master_{block.name}.png").read_bytes())
    manifest = build_manifest(
        area,
        render,
        (width, height),
        levels,
        digest.hexdigest(),
        source_metadata,
        tuple(
            key for key in ("building_heights", "tree_canopy") if (raw_dir / f"{key}.tif").exists()
        )
        + (("wikidata",) if (processed_dir / "pois.json").exists() else ()),
    )
    animation: dict[str, Any] = {}
    if has_overlay:
        animation["overlay_url_template"] = "overlay/{level}/{column}_{row}.{format}"
    if has_front:
        animation["front_url_template"] = "front/{level}/{column}_{row}.{format}"
    if (processed_dir / "motion.json").exists():
        animation["motion_url"] = "motion.json"
    if animation:
        manifest["animation"] = animation
    summary_path = build_dir / "ai" / "summary.json"
    if has_ai and summary_path.exists():
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        manifest["ai"] = {
            "url_template": "ai/{level}/{column}_{row}.{format}",
            "overlay_url_template": "ai_overlay/{level}/{column}_{row}.{format}"
            if has_overlay
            else None,
            "front_overlay_url_template": "ai_front/{level}/{column}_{row}.{format}"
            if has_ai_front
            else None,
            "model": summary["model"],
            "licence": summary["licence"],
            "coverage": summary["coverage"],
            "composed_at": summary["composed_at"],
        }
    output = build_dir / "manifest.json"
    output.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    tile_count = sum(entry["columns"] * entry["rows"] for entry in levels)
    log.info("wrote %d tiles across %d levels and %s", tile_count, len(levels), output)
    return output
