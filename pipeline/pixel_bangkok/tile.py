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
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from PIL import Image

from .config import AreaConfig, RenderConfig, TileConfig
from .crs import MapBounds
from .projection import IsoProjection

log = logging.getLogger(__name__)

MANIFEST_VERSION = 2
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


def write_pyramid(master: Image.Image, tiles_dir: Path, tiles: TileConfig) -> list[dict[str, int]]:
    if tiles_dir.exists():
        shutil.rmtree(tiles_dir)
    levels = level_dimensions(master.width, master.height)
    save_options: dict[str, Any] = {"lossless": tiles.lossless} if tiles.format == "webp" else {}
    for entry in levels:
        size = (entry["width"], entry["height"])
        image = master if size == master.size else master.resize(size, Image.Resampling.BOX)
        entry["columns"] = math.ceil(entry["width"] / tiles.tile_size)
        entry["rows"] = math.ceil(entry["height"] / tiles.tile_size)
        level_dir = tiles_dir / str(entry["level"])
        level_dir.mkdir(parents=True)
        for column in range(entry["columns"]):
            for row in range(entry["rows"]):
                crop = image.crop(tile_box(column, row, *size, tiles.tile_size, tiles.overlap))
                crop.save(level_dir / f"{column}_{row}.{tiles.format}", **save_options)
    return levels


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


def run(
    area: AreaConfig, render: RenderConfig, raw_dir: Path, processed_dir: Path, build_dir: Path
) -> Path:
    master_path = build_dir / "master.png"
    if not master_path.exists():
        raise FileNotFoundError(f"{master_path} not found; run the style stage first")
    metadata_path = processed_dir / "metadata.json"
    source_metadata = (
        json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.exists() else {}
    )
    with Image.open(master_path) as image:
        master = image.convert("RGB")
    levels = write_pyramid(master, build_dir / "tiles", render.tiles)
    manifest = build_manifest(
        area,
        render,
        master.size,
        levels,
        hashlib.sha256(master_path.read_bytes()).hexdigest(),
        source_metadata,
        tuple(
            key for key in ("building_heights", "tree_canopy") if (raw_dir / f"{key}.tif").exists()
        ),
    )
    output = build_dir / "manifest.json"
    output.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    tile_count = sum(entry["columns"] * entry["rows"] for entry in levels)
    log.info("wrote %d tiles across %d levels and %s", tile_count, len(levels), output)
    return output
