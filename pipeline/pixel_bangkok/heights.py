"""Stage 3 (enrich): derive render heights for buildings with explicit provenance.

Order: curated manual override -> OSM `height` -> OSM `building:levels` x floor
height -> height-raster estimate -> unknown default. Source values are never
overwritten; the raster sample is stored next to them as `raster_height_m`.
"""

from __future__ import annotations

import json
import logging
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from . import rasters
from .config import AreaConfig, HeightConfig, RenderConfig
from .crs import MapBounds
from .geojson_io import read_feature_collection, world_geometries, write_feature_collection
from .schemas import HeightProvenance, RoofShape

log = logging.getLogger(__name__)

FEET_TO_METRES = 0.3048
CHEDI_TOWER_TYPES = {"pagoda", "stupa"}
_HEIGHT_PATTERN = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(m|metres?|meters?|ft|feet|')?\s*$", re.I)


def parse_height_m(raw: str | None) -> float | None:
    """Parse an OSM `height` value to metres. Unitless values are metres."""
    if raw is None:
        return None
    match = _HEIGHT_PATTERN.match(raw.replace(",", "."))
    if not match:
        return None
    value = float(match.group(1))
    unit = (match.group(2) or "m").lower()
    if unit in {"ft", "feet", "'"}:
        value *= FEET_TO_METRES
    return value if value > 0 else None


def parse_levels(raw: str | None) -> float | None:
    if raw is None:
        return None
    try:
        value = float(raw.strip().replace(",", "."))
    except ValueError:
        return None
    return value if value > 0 else None


@dataclass(frozen=True)
class DerivedHeight:
    render_height_m: float
    provenance: HeightProvenance
    height_source: str | None
    note: str | None = None


@dataclass(frozen=True)
class RasterSample:
    height_m: float
    pixels: int
    label: str


def derive_height(
    source_height: str | None,
    source_levels: str | None,
    config: HeightConfig,
    manual: dict[str, Any] | None = None,
    raster: RasterSample | None = None,
) -> DerivedHeight:
    if manual is not None and "height_m" in manual:
        return DerivedHeight(float(manual["height_m"]), "manual", "curated", manual.get("note"))
    height = parse_height_m(source_height)
    if height is not None:
        return DerivedHeight(height, "source", "osm-height")
    levels = parse_levels(source_levels)
    if levels is not None:
        return DerivedHeight(
            levels * config.floor_height_m,
            "estimated",
            "osm-levels",
            f"{levels:g} levels x {config.floor_height_m:g} m assumed floor height",
        )
    if raster is not None:
        note = (
            f"{raster.label}: {config.raster_percentile:g}th percentile of "
            f"{raster.pixels} pixels inside the footprint"
        )
        if raster.height_m < config.min_height_m:
            note += f"; raised from {raster.height_m:g} m to the {config.min_height_m:g} m minimum"
        return DerivedHeight(max(raster.height_m, config.min_height_m), "estimated", "raster", note)
    return DerivedHeight(
        config.unknown_height_m, "unknown", None, "no height data; default visual height"
    )


def sample_raster_height(
    layer: rasters.RasterLayer,
    geometry_world: Any,
    bounds: MapBounds,
    config: HeightConfig,
    label: str,
) -> RasterSample | None:
    heights = rasters.footprint_values(layer, "building_height", geometry_world, bounds)
    presence = rasters.footprint_values(layer, "building_presence", geometry_world, bounds)
    valid = (
        (heights != rasters.NODATA)
        & (presence != rasters.NODATA)
        & (presence >= config.raster_presence_threshold)
    )
    pixel_area = abs(layer.transform.a * layer.transform.e)
    if valid.sum() * pixel_area < config.raster_min_area_m2:
        return None
    value = float(np.percentile(heights[valid], config.raster_percentile))
    if value <= 0:
        return None
    return RasterSample(round(value, 2), int(valid.sum()), label)


def load_landmark_overrides(curated_dir: Path) -> dict[str, dict[str, Any]]:
    path = curated_dir / "landmarks.json"
    if not path.exists():
        return {}
    records = json.loads(path.read_text(encoding="utf-8"))["landmarks"]
    return {record["source_id"]: record for record in records}


def roof_shape(properties: dict[str, Any], manual: dict[str, Any] | None) -> RoofShape:
    """Stylised roof form; OSM rarely tags roofs here, so this is a drawing choice."""
    if manual is not None and "roof_shape" in manual:
        return manual["roof_shape"]
    if properties.get("is_tower"):
        return "chedi" if properties.get("tower_type") in CHEDI_TOWER_TYPES else "spire"
    if properties.get("category") == "temple":
        return "gabled"
    return "flat"


def run(
    area: AreaConfig, render: RenderConfig, raw_dir: Path, processed_dir: Path, curated_dir: Path
) -> Path:
    config = render.heights
    bounds = MapBounds.from_area(area)
    collection = read_feature_collection(processed_dir / "buildings.geojson")
    geometries = world_geometries(processed_dir / "buildings.geojson", bounds)
    overrides = load_landmark_overrides(curated_dir)
    raster_path = raw_dir / "building_heights.tif"
    layer = None
    label = None
    if area.building_heights is not None and raster_path.exists():
        layer = rasters.read_layer(raster_path)
        label = f"{area.building_heights.dataset} {area.building_heights.year}"
    elif area.building_heights is not None:
        log.warning("%s missing; run extract to use raster heights", raster_path)
    counts: Counter[str] = Counter()
    unused = set(overrides)
    for feature, (geometry, _) in zip(collection["features"], geometries, strict=True):
        properties = feature["properties"]
        manual = overrides.get(properties["source_id"])
        unused.discard(properties["source_id"])
        sample = (
            sample_raster_height(layer, geometry, bounds, config, label)
            if layer is not None and label is not None
            else None
        )
        derived = derive_height(
            properties["source_height"], properties["source_levels"], config, manual, sample
        )
        properties["raster_height_m"] = sample.height_m if sample else None
        properties["render_height_m"] = round(derived.render_height_m, 2)
        properties["height_provenance"] = derived.provenance
        properties["height_source"] = derived.height_source
        properties["height_note"] = derived.note
        properties["roof_shape"] = roof_shape(properties, manual)
        counts[derived.height_source or "unknown"] += 1
    for source_id in sorted(unused):
        log.warning("curated landmark override matches no building: %s", source_id)
    metadata = dict(collection["metadata"])
    metadata["height_source_counts"] = dict(sorted(counts.items()))
    metadata["height_config"] = config.__dict__
    if layer is not None and area.building_heights is not None:
        metadata["height_raster"] = {
            "dataset": area.building_heights.dataset,
            "year": area.building_heights.year,
            "licence": area.building_heights.licence,
        }
    output = processed_dir / "buildings.enriched.geojson"
    write_feature_collection(output, collection["features"], metadata)
    log.info("height sources: %s -> %s", dict(counts), output)
    return output
