"""Paths for the optional traffic and boat animation layer.

Input: data/raw/<area>/osm.json (Overpass JSON, WGS84).
Output: data/processed/<area>/motion.json with paths in world metres (x east,
y north from the area's south-west corner), clipped to the area. Endpoints
are shared node indexes so the viewer can route vehicles across junctions.
The animation is illustrative: vehicle counts and positions are not data.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from shapely import segmentize
from shapely.geometry import LineString, Point, box
from shapely.geometry.base import BaseGeometry

from .config import AreaConfig, RenderConfig
from .crs import MapBounds
from .geojson_io import world_geometries

log = logging.getLogger(__name__)

ROAD_CLASSES = {
    "motorway": "major",
    "trunk": "major",
    "primary": "major",
    "secondary": "major",
    "tertiary": "minor",
    "unclassified": "minor",
    "residential": "minor",
    "living_street": "minor",
    "service": "service",
}
EXCLUDED_SERVICE = {"parking_aisle", "driveway", "drive-through", "emergency_access"}
WATER_KINDS = {"river": "river", "canal": "canal"}
NODE_PRECISION = 1
MIN_LENGTH_M = 5.0
METRO_KINDS = {"subway", "light_rail", "monorail"}
EXCLUDED_RAIL_SERVICE = {"yard", "siding", "crossover"}
RAIL_SAMPLE_M = 12.0


def _oneway(tags: dict[str, str]) -> int:
    value = tags.get("oneway")
    if value in {"yes", "true", "1"} or tags.get("junction") in {"roundabout", "circular"}:
        return 1
    if value == "-1":
        return -1
    return 0


def classify(tags: dict[str, str]) -> tuple[str, str] | None:
    """Return (layer, class) for a way that vehicles or boats can use."""
    highway = tags.get("highway", "").removesuffix("_link")
    if highway in ROAD_CLASSES and tags.get("service") not in EXCLUDED_SERVICE:
        if tags.get("access") in {"no", "private"} or tags.get("area") == "yes":
            return None
        bridge = tags.get("bridge", "no")
        if bridge == "viaduct" or (bridge != "no" and highway == "motorway"):
            return None
        return "roads", ROAD_CLASSES[highway]
    if tags.get("waterway") in WATER_KINDS:
        return "waterways", WATER_KINDS[tags["waterway"]]
    if tags.get("route") == "ferry":
        return "waterways", "ferry"
    return None


def _parts(geometry: BaseGeometry) -> list[LineString]:
    if isinstance(geometry, LineString):
        return [geometry]
    return [part for part in getattr(geometry, "geoms", []) if isinstance(part, LineString)]


def build_paths(
    elements: list[dict[str, Any]], bounds: MapBounds, render: RenderConfig
) -> dict[str, Any]:
    clip = box(0, 0, bounds.width_m, bounds.height_m)
    nodes: dict[tuple[float, float], int] = {}
    layers: dict[str, list[dict[str, Any]]] = {"roads": [], "waterways": []}

    def node(point: tuple[float, float]) -> int:
        key = (round(point[0], NODE_PRECISION), round(point[1], NODE_PRECISION))
        return nodes.setdefault(key, len(nodes))

    for element in sorted(elements, key=lambda item: (item["type"], item["id"])):
        if element["type"] != "way" or len(element.get("geometry") or []) < 2:
            continue
        tags = element.get("tags", {})
        classified = classify(tags)
        if classified is None:
            continue
        layer, kind = classified
        line = LineString([bounds.lonlat_to_world(p["lon"], p["lat"]) for p in element["geometry"]])
        for part in _parts(line.intersection(clip)):
            if part.length < MIN_LENGTH_M:
                continue
            coords = [(round(x, 1), round(y, 1)) for x, y in part.coords]
            path: dict[str, Any] = {
                "id": f"way/{element['id']}",
                "kind": kind,
                "start": node(coords[0]),
                "end": node(coords[-1]),
                "points": coords,
            }
            if layer == "roads":
                highway = tags["highway"].removesuffix("_link")
                path["oneway"] = _oneway(tags)
                path["width_m"] = float(
                    render.road_widths_m.get(highway, render.road_widths_m["default"])
                )
            layers[layer].append(path)
    return {
        "version": 1,
        "crs": bounds.crs,
        "units": "metres east/north of the area's south-west corner",
        "drive_side": "left",
        "node_count": len(nodes),
        **layers,
    }


def rail_paths(
    features: list[tuple[BaseGeometry, dict[str, Any]]],
    render: RenderConfig,
    node: Any,
) -> list[dict[str, Any]]:
    """Train paths with a height per point: deck top for viaducts, 0 at grade; no tunnels."""
    from .render import deck_height, is_elevated

    paths = []
    for geometry, properties in sorted(features, key=lambda item: item[1]["source_id"]):
        if properties.get("level") == "underground":
            continue
        if properties.get("service") in EXCLUDED_RAIL_SERVICE:
            continue
        for part in _parts(geometry):
            if part.length < MIN_LENGTH_M:
                continue
            dense = segmentize(part, RAIL_SAMPLE_M)
            points = []
            for x, y in dense.coords:
                z = 0.0
                if is_elevated(properties):
                    distance = part.project(Point(x, y))
                    z = deck_height(properties, distance, part.length, render.transit.ramp_grade)
                points.append([round(x, 1), round(y, 1), round(z, 2)])
            paths.append(
                {
                    "id": f"{properties['source_id']}#{properties.get('part', 0)}",
                    "kind": "metro" if properties["category"] in METRO_KINDS else "rail",
                    "start": node((points[0][0], points[0][1])),
                    "end": node((points[-1][0], points[-1][1])),
                    "points": points,
                    "oneway": 0,
                    "width_m": properties["tracks"] * properties["track_width_m"],
                    "colour": properties.get("colour"),
                    "line": properties.get("line"),
                }
            )
    return paths


def run(area: AreaConfig, render: RenderConfig, raw_dir: Path, processed_dir: Path) -> Path:
    raw_path = raw_dir / "osm.json"
    if not raw_path.exists():
        raise FileNotFoundError(f"{raw_path} not found; run the extract stage first")
    elements = json.loads(raw_path.read_text(encoding="utf-8"))["elements"]
    bounds = MapBounds.from_area(area)
    paths = build_paths(elements, bounds, render)
    rail_path = processed_dir / "rail.geojson"
    if rail_path.exists():
        nodes: dict[tuple[float, float], int] = {}

        def node(point: tuple[float, float]) -> int:
            key = (round(point[0], NODE_PRECISION), round(point[1], NODE_PRECISION))
            return nodes.setdefault(key, paths["node_count"] + len(nodes))

        paths["rail"] = rail_paths(world_geometries(rail_path, bounds), render, node)
        paths["node_count"] += len(nodes)
    output = processed_dir / "motion.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(paths, separators=(",", ":")), encoding="utf-8")
    log.info(
        "motion paths: %d roads, %d rail, %d waterways -> %s",
        len(paths["roads"]),
        len(paths.get("rail", [])),
        len(paths["waterways"]),
        output,
    )
    return output
