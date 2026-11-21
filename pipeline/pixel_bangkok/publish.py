"""Stage 7: publish tiles, manifest and projected POIs for the web viewer.

Writes <publish_dir>/{manifest.json,pois.json,tiles/} and refreshes the area
index one directory up. POIs keep their WGS84 coordinates and gain image pixel
coordinates computed with the same projection as the render.
"""

from __future__ import annotations

import json
import logging
import math
import shutil
from pathlib import Path
from typing import Any

from .config import AreaConfig, RenderConfig
from .crs import MapBounds
from .projection import IsoProjection
from .schemas import PointOfInterest, SchemaError
from .tile import PYRAMID_DIRS

log = logging.getLogger(__name__)

DUPLICATE_DISTANCE_M = 25.0
THUMBNAIL_SIZE = (360, 220)


def _read_pois(path: Path) -> list[PointOfInterest]:
    if not path.exists():
        return []
    records = json.loads(path.read_text(encoding="utf-8"))["pois"]
    return [PointOfInterest.from_dict(record) for record in records]


def merge_pois(
    curated: list[PointOfInterest], generated: list[PointOfInterest], bounds: MapBounds
) -> list[PointOfInterest]:
    """Curated POIs win; a generated POI near a curated one of the same category is dropped."""
    merged = list(curated)
    ids = {poi.id for poi in curated}
    anchors = [(poi.category, bounds.lonlat_to_world(poi.lon, poi.lat)) for poi in curated]
    for poi in generated:
        x, y = bounds.lonlat_to_world(poi.lon, poi.lat)
        duplicate = any(
            category == poi.category and math.hypot(x - cx, y - cy) <= DUPLICATE_DISTANCE_M
            for category, (cx, cy) in anchors
        )
        if poi.id in ids or duplicate:
            continue
        ids.add(poi.id)
        merged.append(poi)
    return merged


def load_pois(
    curated_dir: Path, processed_dir: Path | None = None, bounds: MapBounds | None = None
) -> list[PointOfInterest]:
    curated = _read_pois(curated_dir / "pois.json")
    generated = _read_pois(processed_dir / "pois.json") if processed_dir else []
    if not curated and not generated:
        log.warning("no curated or generated POIs for %s", curated_dir.name)
    ids = [poi.id for poi in curated]
    if len(ids) != len(set(ids)):
        raise SchemaError("POI ids must be unique")
    if bounds is None or not generated:
        return curated + [poi for poi in generated if poi.id not in set(ids)]
    return merge_pois(curated, generated, bounds)


def write_thumbnails(pois: list[dict[str, Any]], build_dir: Path, output_dir: Path) -> int:
    """Crop each landmark from the map (AI layer where composed) for the places rail."""
    from .blocks import blocks_of, read_info, read_region

    blocks_dir = build_dir / "blocks"
    try:
        info = read_info(blocks_dir)
    except FileNotFoundError:
        return 0
    blocks = blocks_of(info)
    prefix = (
        "ai_master"
        if all((blocks_dir / f"ai_master_{block.name}.png").exists() for block in blocks)
        else "master"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    half_w, half_h = THUMBNAIL_SIZE[0] // 2, THUMBNAIL_SIZE[1] // 2
    for poi in pois:
        x, y = round(poi["image"]["x"]), round(poi["image"]["y"])
        top = y - int(half_h * 1.4)
        crop = read_region(
            blocks_dir, prefix, (x - half_w, top, x + half_w, top + THUMBNAIL_SIZE[1]), "RGB"
        )
        crop.save(output_dir / f"{poi['id']}.webp", quality=82, method=6)
        poi["thumbnail"] = f"places/{poi['id']}.webp"
    return len(pois)


def project_pois(
    pois: list[PointOfInterest], bounds: MapBounds, projection: IsoProjection
) -> list[dict[str, Any]]:
    projected = []
    for poi in pois:
        x, y = bounds.lonlat_to_world(poi.lon, poi.lat)
        if not bounds.contains_world(x, y):
            log.warning("POI %s lies outside the area bounds and is not published", poi.id)
            continue
        px, py = projection.world_to_master(x, y)
        projected.append(
            {
                "id": poi.id,
                "name_en": poi.name_en,
                "name_th": poi.name_th,
                "aliases": list(poi.aliases),
                "category": poi.category,
                "lon": poi.lon,
                "lat": poi.lat,
                "description": poi.description,
                "source": poi.source,
                "source_url": poi.source_url,
                "icon": poi.icon,
                "rank": poi.rank,
                **({"line": poi.line} if poi.line else {}),
                "image": {"x": round(px, 2), "y": round(py, 2)},
            }
        )
    return projected


def write_index(maps_dir: Path) -> Path:
    areas = []
    for manifest_path in sorted(maps_dir.glob("*/manifest.json")):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        areas.append({"id": manifest["area_id"], "name": manifest["name"]})
    output = maps_dir / "index.json"
    output.write_text(json.dumps({"areas": areas}, indent=2, ensure_ascii=False), encoding="utf-8")
    return output


EDGE_CLEAR_PX = 12
EDGE_MAX_DISSOLVED = 0.05


def visible_pois(
    pois: list[dict], bounds: MapBounds, render: RenderConfig, keep: set[str] = frozenset()
) -> list[dict]:
    """Drop generated places whose spot lies in the dissolved coverage edge
    (see pixelart.edge_dissolve); places in `keep` (curated) always stay."""
    from .pixelart import edge_dissolve

    scale = render.upscale
    kept = []
    for poi in pois:
        x, y = int(poi["image"]["x"] / scale), int(poi["image"]["y"] / scale)
        if poi["id"] in keep:
            kept.append(poi)
            continue
        box = (x - EDGE_CLEAR_PX, y - EDGE_CLEAR_PX, x + EDGE_CLEAR_PX, y + EDGE_CLEAR_PX)
        if float(edge_dissolve(bounds, render, box).mean()) <= EDGE_MAX_DISSOLVED:
            kept.append(poi)
    if len(kept) < len(pois):
        log.info("left out %d places inside the faded map edge", len(pois) - len(kept))
    return kept


def run(
    area: AreaConfig,
    render: RenderConfig,
    build_dir: Path,
    curated_dir: Path,
    publish_dir: Path,
    processed_dir: Path | None = None,
) -> Path:
    manifest_path = build_dir / "manifest.json"
    tiles_dir = build_dir / "tiles"
    if not manifest_path.exists() or not tiles_dir.exists():
        raise FileNotFoundError(f"no tiles or manifest in {build_dir}; run the tile stage first")
    bounds = MapBounds.from_area(area)
    projection = IsoProjection.create(bounds, render)
    pois = visible_pois(
        project_pois(load_pois(curated_dir, processed_dir, bounds), bounds, projection),
        bounds,
        render,
        keep={poi.id for poi in _read_pois(curated_dir / "pois.json")},
    )
    if publish_dir.exists():
        shutil.rmtree(publish_dir)
    publish_dir.mkdir(parents=True)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["projection"]["geographic"] = bounds.browser_transforms()
    (publish_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    for built, published in PYRAMID_DIRS.items():
        if (build_dir / built).exists():
            shutil.copytree(build_dir / built, publish_dir / published)
    if processed_dir is not None and (processed_dir / "motion.json").exists():
        shutil.copy2(processed_dir / "motion.json", publish_dir / "motion.json")
    write_thumbnails(pois, build_dir, publish_dir / "places")
    (publish_dir / "pois.json").write_text(
        json.dumps({"area_id": area.id, "pois": pois}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    index = write_index(publish_dir.parent)
    log.info("published %d POIs and tiles to %s (index: %s)", len(pois), publish_dir, index)
    return publish_dir
