"""Fill gaps in OpenStreetMap's buildings with outlines from Overture Maps.

OpenStreetMap maps only a small share of Bangkok's buildings; most streets away from the centre
have none, so the drawing showed bare ground where the city is built up. Overture's buildings
theme combines OpenStreetMap with machine-traced outlines from Google Open Buildings and
Microsoft, all under ODbL 1.0.

OpenStreetMap stays the reference: only Overture buildings that come from another source and
do not overlap a mapped OpenStreetMap building are added. Each added building keeps its Overture
ID, its original dataset and its licence. Heights are never invented here: Overture's own height
(rare) is kept as a source value, and the enrich stage estimates the rest from the Open Buildings
height raster with `estimated` provenance, like any OSM building without a height.

Input: a GeoParquet file in WGS84 (EPSG:4326), as written by `overturemaps download`.
Output: building features in the processed buildings layer, WGS84 for storage.
"""

from __future__ import annotations

import logging
from collections import Counter
from pathlib import Path
from typing import Any

import pyarrow.compute as pc
import pyarrow.parquet as pq
import shapely
from shapely.geometry import box, shape
from shapely.geometry.base import BaseGeometry
from shapely.strtree import STRtree
from shapely.validation import make_valid

from .config import REPO_ROOT, AreaConfig
from .crs import MapBounds
from .geojson_io import feature

log = logging.getLogger(__name__)

COLUMNS = ["id", "geometry", "sources", "height", "num_floors", "is_underground"]
MAX_OSM_OVERLAP = 0.2
"""An Overture building that shares more than this share of its footprint with an OSM building is
the same building traced twice; the OSM one is kept."""
MAX_WATER_OVERLAP = 0.5
"""Machine-traced outlines on the river are moored boats or noise, not buildings."""
SENSITIVE_GROUND = {"religious", "palace", "military"}
"""Temple, palace and military grounds keep only their mapped buildings: a machine-traced outline
there would draw a temple hall or a throne hall as a plain block."""
ROADS = {
    "motorway",
    "trunk",
    "primary",
    "secondary",
    "tertiary",
    "unclassified",
    "residential",
    "living_street",
    "service",
    "busway",
}
"""A traced outline across the centre line of one of these at-grade roads hides a real road;
footways and paths are left out because they do run through arcades and passages."""
MIN_AREA_M2 = 12.0
"""Smaller traced outlines are mostly sheds, cars and noise; OSM keeps its small buildings."""


def _polygons(geometry: BaseGeometry) -> BaseGeometry | None:
    if geometry.geom_type in {"Polygon", "MultiPolygon"}:
        return geometry
    if geometry.geom_type == "GeometryCollection":
        parts = [g for g in geometry.geoms if g.geom_type in {"Polygon", "MultiPolygon"}]
        return shapely.union_all(parts) if parts else None
    return None


def _world(features: list[dict[str, Any]], bounds: MapBounds) -> list[BaseGeometry]:
    return [bounds.geometry_to_world(shape(item["geometry"])) for item in features]


def read_candidates(path: Path, bounds: MapBounds) -> list[dict[str, Any]]:
    """Rows inside the area's bounding box, not from OpenStreetMap and above ground."""
    south, west, north, east = bounds.geographic_bbox()
    table = pq.read_table(path, columns=[*COLUMNS, "bbox"])
    bbox = table.column("bbox")
    inside = pc.and_(
        pc.and_(
            pc.less_equal(pc.struct_field(bbox, "xmin"), east),
            pc.greater_equal(pc.struct_field(bbox, "xmax"), west),
        ),
        pc.and_(
            pc.less_equal(pc.struct_field(bbox, "ymin"), north),
            pc.greater_equal(pc.struct_field(bbox, "ymax"), south),
        ),
    )
    rows = table.filter(inside).select(COLUMNS).to_pylist()
    rows.sort(key=lambda row: row["id"])
    return rows


def fill(
    layers: dict[str, list[dict[str, Any]]],
    area: AreaConfig,
    bounds: MapBounds,
    path: Path,
) -> dict[str, int]:
    """Append gap-filling buildings to `layers["buildings"]`; return counts for the stats."""
    assert area.building_fill is not None
    stats: Counter[str] = Counter()
    clip = box(0, 0, bounds.width_m, bounds.height_m)
    osm = _world(layers["buildings"], bounds)
    osm_index = STRtree(osm) if osm else None
    water = [
        g for g in _world(layers["water"], bounds) if g.geom_type in {"Polygon", "MultiPolygon"}
    ]
    water_index = STRtree(water) if water else None
    roads = [
        bounds.geometry_to_world(shape(item["geometry"]))
        for item in layers["roads"]
        if item["properties"].get("category") in ROADS
        and not item["properties"].get("bridge")
        and not item["properties"].get("elevated")
        and item["properties"].get("level") != "underground"
    ]
    road_index = STRtree(roads) if roads else None
    grounds = [
        bounds.geometry_to_world(shape(item["geometry"]))
        for item in layers["ground"]
        if item["properties"].get("category") in SENSITIVE_GROUND
    ]
    ground_index = STRtree(grounds) if grounds else None

    for row in read_candidates(path, bounds):
        sources = row["sources"] or []
        dataset = sources[0]["dataset"] if sources else None
        if dataset == "OpenStreetMap" or dataset is None:
            stats["fill_skipped_osm"] += 1
            continue
        if row["is_underground"]:
            stats["fill_skipped_underground"] += 1
            continue
        geometry = bounds.geometry_to_world(shapely.from_wkb(row["geometry"]))
        if not geometry.is_valid:
            geometry = make_valid(geometry)
        clipped = _polygons(geometry.intersection(clip))
        if clipped is None or clipped.is_empty:
            stats["fill_skipped_outside"] += 1
            continue
        if clipped.area < MIN_AREA_M2:
            stats["fill_skipped_small"] += 1
            continue
        if osm_index is not None:
            hits = osm_index.query(clipped, predicate="intersects")
            shared = sum(clipped.intersection(osm[int(i)]).area for i in hits)
            if shared > MAX_OSM_OVERLAP * clipped.area:
                stats["fill_skipped_overlaps_osm"] += 1
                continue
        if ground_index is not None and len(
            ground_index.query(clipped.representative_point(), predicate="within")
        ):
            stats["fill_skipped_sensitive_ground"] += 1
            continue
        if road_index is not None and len(road_index.query(clipped, predicate="intersects")):
            stats["fill_skipped_on_road"] += 1
            continue
        if water_index is not None:
            hits = water_index.query(clipped, predicate="intersects")
            wet = sum(clipped.intersection(water[int(i)]).area for i in hits)
            if wet > MAX_WATER_OVERLAP * clipped.area:
                stats["fill_skipped_water"] += 1
                continue
        height = row["height"]
        floors = row["num_floors"]
        properties = {
            "source_id": f"overture/{row['id']}",
            "source": f"{area.building_fill.dataset} {area.building_fill.release}",
            "source_dataset": dataset,
            "source_licence": sources[0].get("license"),
            "name": None,
            "name_en": None,
            "name_th": None,
            "category": "yes",
            "is_temple": False,
            "is_tower": False,
            "tower_type": None,
            "source_height": f"{height:g}" if height else None,
            "source_levels": f"{floors:d}" if floors else None,
            "clipped": not clipped.equals(geometry),
        }
        layers["buildings"].append(feature(clipped, properties, bounds))
        stats["fill_added"] += 1
        stats[f"fill_added_{dataset.lower().replace(' ', '_')}"] += 1
    return dict(stats)


def run(layers: dict[str, list[dict[str, Any]]], area: AreaConfig, bounds: MapBounds) -> dict:
    """Fill when the area configures a source and its file is present; otherwise do nothing."""
    if area.building_fill is None:
        return {}
    path = REPO_ROOT / area.building_fill.path
    if not path.exists():
        log.warning("building fill skipped: %s not found", path)
        return {}
    stats = fill(layers, area, bounds, path)
    log.info("building fill: %s", stats)
    return stats
