"""Stage 3 (enrich): derive render heights for buildings with explicit provenance.

Order: curated manual override -> OSM `height` -> Wikidata height (P2048) of the
item the building links to -> OSM `building:levels` x floor height ->
height-raster estimate -> unknown default. Source values are never overwritten;
the raster sample is stored next to them as `raster_height_m`.

The Open Buildings 2.5D raster has no values above about 100 m (none above
99.5 m over the 20 km Bangkok area), so raster heights at that ceiling are
marked as possibly lower than the real building.
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


MAX_PLAUSIBLE_HEIGHT_M = 830.0
MAX_PLAUSIBLE_LEVELS = 163


RASTER_CEILING_M = 99.0
METRE = "http://www.wikidata.org/entity/Q11573"
FOOT = "http://www.wikidata.org/entity/Q3710"


@dataclass(frozen=True)
class WikidataHeight:
    height_m: float
    qid: str


def wikidata_height(claims: dict[str, Any]) -> float | None:
    """Height (P2048) in metres from an item's claims: preferred statements first, the tallest
    if several remain; deprecated statements and unknown units are ignored."""
    statements = [s for s in claims.get("P2048", []) if s.get("rank") != "deprecated"]
    preferred = [s for s in statements if s.get("rank") == "preferred"]
    values = []
    for statement in preferred or statements:
        value = statement.get("mainsnak", {}).get("datavalue", {}).get("value", {})
        try:
            amount = float(value.get("amount", ""))
        except ValueError:
            continue
        unit = value.get("unit")
        if unit == METRE:
            values.append(amount)
        elif unit == FOOT:
            values.append(amount * FEET_TO_METRES)
    return max(values) if values else None


def fetch_wikidata_heights(qids: list[str], cache_path: Path) -> dict[str, float | None]:
    """Heights for Wikidata items, cached in `cache_path` (None = item has no usable height)."""
    import time
    import urllib.parse

    from .pois import BATCH_PAUSE_S, BATCH_SIZE, WIKIDATA_API, _get_entities

    cache: dict[str, float | None] = (
        json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    )
    missing = sorted(qid for qid in set(qids) if qid not in cache)
    for start in range(0, len(missing), BATCH_SIZE):
        batch = missing[start : start + BATCH_SIZE]
        query = urllib.parse.urlencode(
            {"action": "wbgetentities", "ids": "|".join(batch), "props": "claims", "format": "json"}
        )
        entities = _get_entities(f"{WIKIDATA_API}?{query}")
        for qid in batch:
            cache[qid] = wikidata_height(entities.get(qid, {}).get("claims", {}))
        cache_path.write_text(json.dumps(cache, indent=1, sort_keys=True), encoding="utf-8")
        time.sleep(BATCH_PAUSE_S)
    return cache


def derive_height(
    source_height: str | None,
    source_levels: str | None,
    config: HeightConfig,
    manual: dict[str, Any] | None = None,
    raster: RasterSample | None = None,
    wikidata: WikidataHeight | None = None,
) -> DerivedHeight:
    if manual is not None and "height_m" in manual:
        return DerivedHeight(float(manual["height_m"]), "manual", "curated", manual.get("note"))
    rejected = []
    height = parse_height_m(source_height)
    if height is not None and height > MAX_PLAUSIBLE_HEIGHT_M:
        rejected.append(f"implausible OSM height {source_height!r} ignored")
        height = None
    if height is not None:
        return DerivedHeight(height, "source", "osm-height")
    if wikidata is not None and 0 < wikidata.height_m <= MAX_PLAUSIBLE_HEIGHT_M:
        return DerivedHeight(
            wikidata.height_m,
            "source",
            "wikidata",
            f"Wikidata {wikidata.qid} height (P2048), which may include a spire",
        )
    levels = parse_levels(source_levels)
    if levels is not None and levels > MAX_PLAUSIBLE_LEVELS:
        rejected.append(f"implausible OSM building:levels {source_levels!r} ignored")
        levels = None
    if rejected:
        fallback = derive_height(None, None, config, None, raster, wikidata)
        note = "; ".join([*rejected, fallback.note or ""]).rstrip("; ")
        return DerivedHeight(
            fallback.render_height_m, fallback.provenance, fallback.height_source, note
        )
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
        if raster.height_m >= RASTER_CEILING_M:
            note += "; at the raster's ~100 m ceiling, so the real building may be taller"
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


def building_wikidata(osm_path: Path) -> dict[str, str]:
    """OSM building id -> Wikidata QID, from the raw extract."""
    if not osm_path.exists():
        return {}
    links = {}
    for element in json.loads(osm_path.read_text(encoding="utf-8"))["elements"]:
        tags = element.get("tags", {})
        qid = tags.get("wikidata", "")
        if "building" in tags and re.fullmatch(r"Q\d+", qid):
            links[f"{element['type']}/{element['id']}"] = qid
    return links


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
    links = building_wikidata(raw_dir / "osm.json")
    linked = {
        properties["source_id"]: links[properties["source_id"]]
        for properties in (feature["properties"] for feature in collection["features"])
        if properties["source_id"] in links
    }
    heights = fetch_wikidata_heights(
        sorted(set(linked.values())), raw_dir / "wikidata-heights.json"
    )
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
        qid = linked.get(properties["source_id"])
        known = heights.get(qid) if qid else None
        derived = derive_height(
            properties["source_height"],
            properties["source_levels"],
            config,
            manual,
            sample,
            WikidataHeight(known, qid) if known and qid else None,
        )
        properties["raster_height_m"] = sample.height_m if sample else None
        properties["render_height_m"] = round(derived.render_height_m, 2)
        properties["height_provenance"] = derived.provenance
        properties["height_source"] = derived.height_source
        properties["height_note"] = derived.note
        properties["roof_shape"] = roof_shape(properties, manual)
        if manual is not None and "facade" in manual:
            properties["facade"] = manual["facade"]
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
