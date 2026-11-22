"""Stage 2: validate, clip and classify raw OSM elements.

Input: data/raw/<area>/osm.json (Overpass JSON, WGS84 lon/lat).
Geometry operations run in world metres (the area's projected CRS).
Output: data/processed/<area>/{buildings,roads,rail,water,green,ground,trees}.geojson
in WGS84 lon/lat plus metadata.json with counts and provenance.

Elevated roads and rail carry `elevation_m` estimated from the OSM `layer` tag
(`elevation_provenance: "estimated-layer"`) and `ramp_start`/`ramp_end` where
the way meets the same network at grade.
"""

from __future__ import annotations

import json
import logging
import re
from collections import Counter
from pathlib import Path
from typing import Any

from shapely import make_valid
from shapely.geometry import LineString, MultiLineString, MultiPolygon, Point, Polygon, box
from shapely.geometry.base import BaseGeometry
from shapely.ops import polygonize, unary_union

from .config import AreaConfig, RenderConfig
from .crs import MapBounds
from .geojson_io import feature, write_feature_collection
from .heights import parse_height_m

log = logging.getLogger(__name__)

LAYERS = ("buildings", "building_parts", "roads", "rail", "water", "green", "ground", "trees")
RAIL_KINDS = {"rail", "light_rail", "subway", "monorail", "narrow_gauge", "tram"}
METRO_KINDS = {"light_rail", "subway", "monorail"}
TRANSIT_ROUTES = {"train", "subway", "light_rail", "monorail", "tram"}
ELEVATED_ROAD_CATEGORIES = {"motorway"}
DEFAULT_TRACK_WIDTH_M = {"monorail": 3.5}
RAMP_SNAP_M = 0.05
HEX_COLOUR = re.compile(r"^#[0-9a-fA-F]{6}$")
GROUND_LANDUSE = {
    "religious": "religious",
    "residential": "residential",
    "commercial": "commercial",
    "retail": "commercial",
    "education": "institutional",
    "institutional": "institutional",
    "military": "military",
}
GROUND_AMENITY = {
    "place_of_worship": "religious",
    "parking": "parking",
    "school": "institutional",
    "university": "institutional",
    "college": "institutional",
    "hospital": "institutional",
}
PAVED_AREA_HIGHWAYS = {"pedestrian", "footway", "service"}
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


def _ground_category(tags: dict[str, str]) -> str | None:
    if tags.get("area") == "yes" and tags.get("highway") in PAVED_AREA_HIGHWAYS:
        return "paved"
    if tags.get("place") == "square":
        return "paved"
    if tags.get("historic") in {"castle", "palace"}:
        return "palace"
    if tags.get("amenity") in GROUND_AMENITY:
        return GROUND_AMENITY[tags["amenity"]]
    if tags.get("landuse") in GROUND_LANDUSE:
        return GROUND_LANDUSE[tags["landuse"]]
    return None


def _bridge(tags: dict[str, str]) -> str | None:
    value = tags.get("bridge")
    return None if value in (None, "no") else value


def _layer(tags: dict[str, str]) -> int:
    try:
        return int(float(tags.get("layer", "0").split(";")[0]))
    except ValueError:
        return 0


def _elevation(tags: dict[str, str], minimum: float, render: RenderConfig) -> dict[str, Any]:
    level = max(_layer(tags), 1) * render.transit.layer_height_m
    return {"elevation_m": max(minimum, level), "elevation_provenance": "estimated-layer"}


def _rail_level(tags: dict[str, str], category: str) -> str:
    tunnel = tags.get("tunnel")
    if (tunnel not in (None, "no", "building_passage")) or _layer(tags) < 0:
        return "underground"
    bridge = _bridge(tags)
    if bridge == "viaduct" or (bridge and category in METRO_KINDS):
        return "elevated"
    return "ground"


def _tracks(tags: dict[str, str]) -> int:
    try:
        return max(1, int(tags.get("tracks", "1")))
    except ValueError:
        return 1


def _rail(tags: dict[str, str], render: RenderConfig) -> dict[str, Any]:
    category = tags["railway"]
    level = _rail_level(tags, category)
    colour = tags.get("colour")
    properties: dict[str, Any] = {
        "category": category,
        "level": level,
        "tracks": _tracks(tags),
        "track_width_m": DEFAULT_TRACK_WIDTH_M.get(category, render.transit.track_spacing_m),
        "service": tags.get("service"),
        "line": tags.get("name:en") or tags.get("name"),
        "line_th": tags.get("name:th") or tags.get("name"),
        "colour": colour if colour and HEX_COLOUR.match(colour) else None,
        "network": tags.get("network"),
    }
    if level == "elevated":
        properties |= _elevation(tags, render.transit.rail_min_elevation_m, render)
    return properties


def transit_routes(elements: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    """Way id -> line name and colour from route relations; metro lines win over mainline trains."""

    def rank(element: dict[str, Any]) -> tuple[int, int]:
        tags = element["tags"]
        name = f"{tags.get('name:en', '')} {tags.get('ref', '')}"
        if tags.get("route") in {"subway", "light_rail", "monorail"}:
            tier = 0
        elif "Line" in name or "Link" in name:
            tier = 1
        else:
            tier = 2
        return tier, element["id"]

    routes = sorted(
        (
            element
            for element in elements
            if element["type"] == "relation"
            and element.get("tags", {}).get("type") == "route"
            and element["tags"].get("route") in TRANSIT_ROUTES
        ),
        key=rank,
    )
    lines: dict[int, dict[str, Any]] = {}
    for route in routes:
        tags = route["tags"]
        name = tags.get("name:en") or tags.get("name")
        line = {
            "line": re.sub(r"\s*\(.*\)$", "", name) if name else None,
            "line_th": re.sub(r"\s*\(.*\)$", "", tags.get("name", "")) or None,
            "colour": tags["colour"] if HEX_COLOUR.match(tags.get("colour", "")) else None,
            "network": tags.get("network"),
            "line_source": f"relation/{route['id']}",
        }
        for member in route.get("members", []):
            if member.get("type") == "way":
                lines.setdefault(member["ref"], line)
    return lines


def building_part(tags: dict[str, str]) -> dict[str, Any] | None:
    """A building:part's sourced vertical extent; None values mean it is not in the data.

    The renderer only draws a building from its parts when every part has both values, so
    nothing is guessed. Returns None for `building:part=no`.
    """
    if tags.get("building:part") == "no":
        return None
    height = parse_height_m(tags.get("height"))
    if "min_height" in tags:
        min_height = parse_height_m(tags["min_height"])
    elif tags.get("building:min_level", "0") not in {"0", ""}:
        min_height = None
    else:
        min_height = 0.0
    if height is not None and (height <= 0 or (min_height is not None and min_height >= height)):
        height = None
    return {"category": tags["building:part"], "height_m": height, "min_height_m": min_height}


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
    ground = _ground_category(tags)
    if ground is not None and kind != "node":
        return "ground", True, {"category": ground}
    if tags.get("railway") in RAIL_KINDS and kind == "way":
        return "rail", False, _rail(tags, render)
    if "highway" in tags and kind == "way":
        category = tags["highway"].removesuffix("_link")
        bridge = _bridge(tags)
        properties = _width(tags, category, render.road_widths_m) | {
            "category": category,
            "bridge": bridge is not None,
            "elevated": bridge == "viaduct"
            or (bridge is not None and category in ELEVATED_ROAD_CATEGORIES),
        }
        if properties["elevated"]:
            properties |= _elevation(tags, render.transit.road_min_elevation_m, render)
        return "roads", False, properties
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
    pieces: list[tuple[str, LineString, dict[str, Any]]] = []
    at_grade: dict[str, set[tuple[int, int]]] = {"roads": set(), "rail": set()}
    stats: Counter[str] = Counter()
    seen: set[tuple[str, bytes]] = set()

    lines = transit_routes(raw["elements"])
    for element in sorted(raw["elements"], key=lambda item: (item["type"], item["id"])):
        stats["input_elements"] += 1
        tags = element.get("tags", {})
        if "building:part" in tags and "building" not in tags:
            part = building_part(tags)
            if part is None:
                stats["skipped_building_parts"] += 1
                continue
            if part["height_m"] is None or part["min_height_m"] is None:
                stats["building_parts_without_height"] += 1
            classified: tuple[str, bool, dict] | None = ("building_parts", True, part)
        else:
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
        if layer == "rail" and element["id"] in lines and element["type"] == "way":
            line = lines[element["id"]]
            properties |= {
                key: value
                for key, value in line.items()
                if value is not None and (key != "colour" or properties["colour"] is None)
            }
        if layer in {"roads", "rail"} and _is_elevated(properties):
            for part in _line_parts(clipped):
                pieces.append((layer, part, properties))
            continue
        if layer in at_grade and properties.get("level") != "underground":
            for line in _line_parts(clipped):
                at_grade[layer].update(_key(x, y) for x, y in line.coords)
        layers[layer].append(feature(clipped, properties, bounds))
        stats[f"output_{layer}"] += 1

    for layer, part, properties in _with_ramps(pieces, at_grade, clip):
        layers[layer].append(feature(part, properties, bounds))
        stats[f"output_{layer}"] += 1
        stats[f"elevated_{layer}"] += 1

    return layers, dict(sorted(stats.items()))


def _is_elevated(properties: dict[str, Any]) -> bool:
    return bool(properties.get("elevated")) or properties.get("level") == "elevated"


def _line_parts(geometry: BaseGeometry) -> list[LineString]:
    if isinstance(geometry, LineString):
        return [geometry]
    if isinstance(geometry, MultiLineString):
        return list(geometry.geoms)
    return [part for part in getattr(geometry, "geoms", []) if isinstance(part, LineString)]


def _key(x: float, y: float) -> tuple[int, int]:
    return round(x / RAMP_SNAP_M), round(y / RAMP_SNAP_M)


def _with_ramps(
    pieces: list[tuple[str, LineString, dict[str, Any]]],
    at_grade: dict[str, set[tuple[int, int]]],
    clip: Polygon,
) -> list[tuple[str, LineString, dict[str, Any]]]:
    """An elevated end ramps down where it meets the same network at grade, not mid-air."""
    elevated_ends: dict[str, Counter[tuple[int, int]]] = {"roads": Counter(), "rail": Counter()}
    for layer, part, _ in pieces:
        for x, y in (part.coords[0], part.coords[-1]):
            elevated_ends[layer][_key(x, y)] += 1
    edge = clip.exterior
    result = []
    for index, (layer, part, properties) in enumerate(
        sorted(pieces, key=lambda item: (item[0], item[2]["source_id"], item[1].wkb))
    ):
        ends = []
        for x, y in (part.coords[0], part.coords[-1]):
            key = _key(x, y)
            ends.append(
                elevated_ends[layer][key] == 1
                and key in at_grade[layer]
                and edge.distance(Point(x, y)) > 1.0
            )
        result.append(
            (
                layer,
                part,
                properties | {"ramp_start": ends[0], "ramp_end": ends[1], "part": index},
            )
        )
    return result


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
            "building:part elements kept with their sourced height and min_height (None when "
            "missing); the renderer draws a building from its parts only when all are known",
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
