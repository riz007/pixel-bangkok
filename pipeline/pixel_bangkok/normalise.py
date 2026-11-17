"""Stage 2: validate, clip and classify raw OSM elements.

Input: data/raw/<area>/osm.json (Overpass JSON, WGS84 lon/lat).
Geometry operations run in world metres (the area's projected CRS).
Output: data/processed/<area>/{buildings,roads,water,green,trees}.geojson in
WGS84 lon/lat plus metadata.json with counts and provenance.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from pathlib import Path
from typing import Any

from shapely import make_valid
from shapely.geometry import LineString, MultiPolygon, Point, Polygon, box
from shapely.geometry.base import BaseGeometry
from shapely.ops import polygonize, unary_union

from .config import AreaConfig, RenderConfig
from .crs import MapBounds
from .geojson_io import feature, write_feature_collection
from .heights import parse_height_m

log = logging.getLogger(__name__)

LAYERS = ("buildings", "roads", "water", "green", "trees")
GREEN_LEISURE = {"park", "garden", "pitch", "playground"}
GREEN_LANDUSE = {"grass", "forest", "meadow", "recreation_ground", "village_green"}
GREEN_NATURAL = {"wood", "scrub"}
TEMPLE_BUILDINGS = {"temple", "shrine", "monastery"}
MIN_POLYGON_AREA_M2 = 0.5
MIN_LINE_LENGTH_M = 0.5


def _ring_coords(geometry: list[dict[str, float]], bounds: MapBounds) -> list[tuple[float, float]]:
    return [bounds.lonlat_to_world(point["lon"], point["lat"]) for point in geometry]


def _is_closed(coords: list[tuple[float, float]]) -> bool:
    return len(coords) >= 4 and coords[0] == coords[-1]


def _multipolygon(element: dict[str, Any], bounds: MapBounds) -> BaseGeometry | None:
    outers: list[LineString] = []
    inners: list[LineString] = []
    for member in element.get("members", []):
        if member.get("type") != "way" or not member.get("geometry"):
            continue
        coords = _ring_coords(member["geometry"], bounds)
        if len(coords) < 2:
            continue
        (inners if member.get("role") == "inner" else outers).append(LineString(coords))
    if not outers:
        return None
    shell = unary_union(list(polygonize(unary_union(outers))))
    if shell.is_empty:
        return None
    if inners:
        holes = unary_union(list(polygonize(unary_union(inners))))
        shell = shell.difference(holes)
    return shell


def _element_geometry(
    element: dict[str, Any], bounds: MapBounds, as_area: bool
) -> BaseGeometry | None:
    kind = element["type"]
    if kind == "node":
        return Point(bounds.lonlat_to_world(element["lon"], element["lat"]))
    if kind == "way":
        coords = _ring_coords(element.get("geometry") or [], bounds)
        if len(coords) < 2:
            return None
        if as_area:
            return Polygon(coords) if _is_closed(coords) else None
        return LineString(coords)
    if kind == "relation" and as_area:
        return _multipolygon(element, bounds)
    return None


def _polygons_only(geometry: BaseGeometry) -> BaseGeometry | None:
    parts = [
        part
        for part in getattr(geometry, "geoms", [geometry])
        if isinstance(part, (Polygon, MultiPolygon)) and part.area >= MIN_POLYGON_AREA_M2
    ]
    if not parts:
        return None
    return parts[0] if len(parts) == 1 else unary_union(parts)


def _lines_only(geometry: BaseGeometry) -> BaseGeometry | None:
    parts = [
        part
        for part in getattr(geometry, "geoms", [geometry])
        if part.geom_type in {"LineString", "MultiLineString"} and part.length >= MIN_LINE_LENGTH_M
    ]
    if not parts:
        return None
    return parts[0] if len(parts) == 1 else unary_union(parts)


def _base_properties(element: dict[str, Any], area: AreaConfig) -> dict[str, Any]:
    tags = element.get("tags", {})
    return {
        "source_id": f"{element['type']}/{element['id']}",
        "source": area.source.provider,
        "name": tags.get("name"),
        "name_en": tags.get("name:en"),
        "name_th": tags.get("name:th"),
    }


def classify(element: dict[str, Any], render: RenderConfig) -> tuple[str, bool, dict] | None:
    """Return (layer, is_area, extra properties) or None when the element is not rendered."""
    tags = element.get("tags", {})
    kind = element["type"]
    building = tags.get("building")
    if building and building != "no" and kind != "node":
        return (
            "buildings",
            True,
            {
                "category": building,
                "is_temple": building in TEMPLE_BUILDINGS
                or tags.get("amenity") == "place_of_worship",
                "is_tower": tags.get("man_made") in {"tower", "stupa"},
                "tower_type": tags.get("tower:type")
                or ("stupa" if tags.get("man_made") == "stupa" else None),
                "source_height": tags.get("height"),
                "source_levels": tags.get("building:levels"),
            },
        )
    if "highway" in tags and kind == "way":
        category = tags["highway"].removesuffix("_link")
        return (
            "roads",
            False,
            _width(tags, category, render.road_widths_m)
            | {
                "category": category,
                "bridge": tags.get("bridge") not in (None, "no"),
            },
        )
    if tags.get("man_made") == "pier" and kind == "way":
        geometry = element.get("geometry") or []
        closed = len(geometry) >= 4 and geometry[0] == geometry[-1]
        return (
            "roads",
            closed,
            _width(tags, "pier", render.road_widths_m)
            | {
                "category": "pier",
                "bridge": False,
            },
        )
    if tags.get("natural") == "water" and kind != "node":
        return (
            "water",
            True,
            {"category": tags.get("water", "water"), "width_m": None, "width_provenance": None},
        )
    waterway = tags.get("waterway")
    if waterway and waterway not in {"river", "riverbank"} and kind == "way":
        return (
            "water",
            False,
            _width(tags, waterway, render.waterway_widths_m) | {"category": waterway},
        )
    green = (
        tags.get("leisure") in GREEN_LEISURE
        or tags.get("landuse") in GREEN_LANDUSE
        or tags.get("natural") in GREEN_NATURAL
    )
    if green and kind != "node":
        category = tags.get("leisure") or tags.get("landuse") or tags["natural"]
        return "green", True, {"category": category}
    if tags.get("natural") == "tree" and kind == "node":
        return "trees", False, {}
    return None


def _width(tags: dict[str, str], category: str, defaults: dict[str, float]) -> dict[str, Any]:
    sourced = parse_height_m(tags.get("width"))
    if sourced is not None:
        return {"width_m": sourced, "width_provenance": "source"}
    return {
        "width_m": float(defaults.get(category, defaults["default"])),
        "width_provenance": "estimated",
    }


def normalise(
    raw: dict[str, Any], area: AreaConfig, render: RenderConfig
) -> tuple[dict[str, list[dict]], dict[str, Any]]:
    bounds = MapBounds.from_area(area)
    clip = box(0, 0, bounds.width_m, bounds.height_m)
    layers: dict[str, list[dict]] = {layer: [] for layer in LAYERS}
    stats: Counter[str] = Counter()
    seen: set[tuple[str, bytes]] = set()

    for element in sorted(raw["elements"], key=lambda item: (item["type"], item["id"])):
        stats["input_elements"] += 1
        tags = element.get("tags", {})
        if "building:part" in tags and "building" not in tags:
            stats["skipped_building_parts"] += 1
            continue
        classified = classify(element, render)
        if classified is None:
            stats["skipped_unclassified"] += 1
            continue
        layer, as_area, extra = classified
        geometry = _element_geometry(element, bounds, as_area)
        if geometry is None or geometry.is_empty:
            stats["skipped_no_geometry"] += 1
            continue
        if not geometry.is_valid:
            geometry = make_valid(geometry)
            stats["repaired_invalid"] += 1
        clipped = geometry.intersection(clip)
        if as_area:
            clipped = _polygons_only(clipped)
        elif layer != "trees":
            clipped = _lines_only(clipped)
        if clipped is None or clipped.is_empty:
            stats["skipped_outside_bounds"] += 1
            continue
        key = (layer, clipped.normalize().wkb)
        if key in seen:
            stats["skipped_duplicates"] += 1
            continue
        seen.add(key)
        properties = _base_properties(element, area) | extra
        properties["clipped"] = not clipped.equals(geometry)
        layers[layer].append(feature(clipped, properties, bounds))
        stats[f"output_{layer}"] += 1

    return layers, dict(sorted(stats.items()))


def run(area: AreaConfig, render: RenderConfig, raw_dir: Path, processed_dir: Path) -> Path:
    raw_path = raw_dir / "osm.json"
    if not raw_path.exists():
        raise FileNotFoundError(f"{raw_path} not found; run the extract stage first")
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    extract_metadata_path = raw_dir / "extract-metadata.json"
    extract_metadata = (
        json.loads(extract_metadata_path.read_text(encoding="utf-8"))
        if extract_metadata_path.exists()
        else {}
    )
    extract_metadata = extract_metadata.get("osm", extract_metadata)
    layers, stats = normalise(raw, area, render)
    bounds = MapBounds.from_area(area)
    provenance = {
        "area_id": area.id,
        "provider": area.source.provider,
        "dataset": area.source.dataset,
        "licence": area.source.licence,
        "attribution": area.source.attribution,
        "retrieved_at": extract_metadata.get("retrieved_at"),
        "osm_base_timestamp": extract_metadata.get("osm_base_timestamp"),
        "processing": [
            "reprojected WGS84 -> area CRS for geometry operations",
            "invalid geometries repaired with shapely.make_valid",
            "clipped to the area rectangle",
            "exact duplicate geometries removed per layer",
            "building:part elements skipped",
            "reprojected to WGS84 for storage",
        ],
    }
    for layer, features in layers.items():
        write_feature_collection(processed_dir / f"{layer}.geojson", features, provenance)
    metadata_path = processed_dir / "metadata.json"
    metadata_path.write_text(
        json.dumps(
            {**provenance, "bounds": bounds.to_dict(), "stats": stats},
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    log.info("normalise stats: %s", stats)
    log.info("wrote processed layers to %s", processed_dir)
    return metadata_path
