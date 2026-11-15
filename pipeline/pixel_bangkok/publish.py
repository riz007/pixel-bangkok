"""Stage 7: publish tiles, manifest and projected POIs for the web viewer.

Writes <publish_dir>/{manifest.json,pois.json,tiles/} and refreshes the area
index one directory up. POIs keep their WGS84 coordinates and gain image pixel
coordinates computed with the same projection as the render.
"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import Any

from .config import AreaConfig, RenderConfig
from .crs import MapBounds
from .projection import IsoProjection
from .schemas import PointOfInterest, SchemaError

log = logging.getLogger(__name__)


def load_pois(curated_dir: Path) -> list[PointOfInterest]:
    path = curated_dir / "pois.json"
    if not path.exists():
        log.warning("no curated POIs at %s", path)
        return []
    records = json.loads(path.read_text(encoding="utf-8"))["pois"]
    pois = [PointOfInterest.from_dict(record) for record in records]
    ids = [poi.id for poi in pois]
    if len(ids) != len(set(ids)):
        raise SchemaError("POI ids must be unique")
    return pois


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


def run(
    area: AreaConfig, render: RenderConfig, build_dir: Path, curated_dir: Path, publish_dir: Path
) -> Path:
    manifest_path = build_dir / "manifest.json"
    tiles_dir = build_dir / "tiles"
    if not manifest_path.exists() or not tiles_dir.exists():
        raise FileNotFoundError(f"no tiles or manifest in {build_dir}; run the tile stage first")
    bounds = MapBounds.from_area(area)
    projection = IsoProjection.create(bounds, render)
    pois = project_pois(load_pois(curated_dir), bounds, projection)
    if publish_dir.exists():
        shutil.rmtree(publish_dir)
    publish_dir.mkdir(parents=True)
    shutil.copytree(tiles_dir, publish_dir / "tiles")
    shutil.copy2(manifest_path, publish_dir / "manifest.json")
    (publish_dir / "pois.json").write_text(
        json.dumps({"area_id": area.id, "pois": pois}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    index = write_index(publish_dir.parent)
    log.info("published %d POIs and tiles to %s (index: %s)", len(pois), publish_dir, index)
    return publish_dir
