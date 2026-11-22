"""Sensitive places (worship, palaces, military land, monuments) and their protection from AI.

A sensitive place is a temple or palace compound with every building inside it, or a single
sensitive building. Shapes come from the processed OSM layers (world metres) and the POI files,
and are drawn in native image pixels with the render's own projection; each building is covered
by its whole silhouette (walls and roof, not only its footprint), plus a margin.

By default ("auto") the AI paints everything, and a place keeps the plain drawing only when the
AI made it unrecognisable: it lost most of the gilding or the tiled temple roofs, or its outlines
moved (`recognisable`). A curated file can force a place either way.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from shapely.geometry import MultiPolygon, Point, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union
from shapely.prepared import prep
from shapely.strtree import STRtree

from .crs import MapBounds
from .projection import IsoProjection

BUILDING_CATEGORIES = {
    "temple",
    "chapel",
    "church",
    "cathedral",
    "mosque",
    "shrine",
    "synagogue",
    "monastery",
    "religious",
    "palace",
    "government",
    "military",
}
TOWER_TYPES = {"stupa", "pagoda", "bell_tower"}
ROOF_SHAPES = {"prang", "chedi"}
GROUND_CATEGORIES = {"religious", "palace", "military"}
POI_CATEGORIES = {"temple", "historic"}
# Landmark POIs that are sacred or royal but carry a neutral category.
POI_IDS = {"giant-swing", "democracy-monument"}
MARGIN_M = 4.0
POI_SNAP_M = 15.0
"""A protected POI protects the drawn buildings within this distance of its point. A bare circle
would paste a patch of plain drawing into the AI art without protecting anything drawn."""
FEATHER_PX = 3

Shape = tuple[Polygon, float]
PROTECT_MODES = ("auto", "all", "none")
# HSV ranges (PIL scale, 0-255) for the colours that make a Thai temple recognisable.
GOLD = ((25, 45), 110, 120)
TEMPLE_ROOF = ((6, 22), 110, 90)
MIN_SIGNATURE = 0.02
"""A colour counts towards a place's identity when it covers this share of the place."""
MIN_RETAINED = 0.6
MIN_PLACE_RECALL = 0.75


@dataclass
class Place:
    id: str
    name: str | None
    shapes: list[Shape] = field(default_factory=list)


def building_is_protected(properties: dict[str, Any]) -> bool:
    return bool(
        properties.get("is_temple")
        or properties.get("category") in BUILDING_CATEGORIES
        or properties.get("tower_type") in TOWER_TYPES
        or properties.get("roof_shape") in ROOF_SHAPES
    )


def _polygons(geometry: BaseGeometry) -> list[Polygon]:
    if isinstance(geometry, Polygon):
        return [geometry]
    if isinstance(geometry, MultiPolygon):
        return list(geometry.geoms)
    return []


def sensitive_places(
    layers: dict[str, list[tuple[BaseGeometry, dict[str, Any]]]],
    pois: list[dict[str, Any]],
    bounds: MapBounds,
) -> list[Place]:
    """Compounds (with the buildings inside) and standalone sensitive buildings, by source ID."""
    from .render import parts_by_building

    places: list[Place] = []
    compounds: list[tuple[Any, Place]] = []
    for geometry, properties in layers.get("ground", []):
        if properties.get("category") not in GROUND_CATEGORIES:
            continue
        name = properties.get("name_en") or properties.get("name")
        place = Place(properties.get("source_id", f"compound/{len(places)}"), name)
        place.shapes += [(p, 0.0) for p in _polygons(geometry.buffer(MARGIN_M))]
        compounds.append((geometry, place))
        places.append(place)
    index = STRtree([geometry for geometry, _ in compounds]) if compounds else None
    points = [
        Point(*bounds.lonlat_to_world(float(poi["lon"]), float(poi["lat"])))
        for poi in pois
        if poi.get("category") in POI_CATEGORIES or poi.get("id") in POI_IDS
    ]
    near_poi = prep(unary_union([point.buffer(POI_SNAP_M) for point in points])) if points else None
    members: dict[str, Place] = {}
    kept = []
    for geometry, properties in layers.get("buildings", []):
        point = geometry.representative_point()
        owner = None
        if index is not None:
            for hit in index.query(point, predicate="within"):
                owner = compounds[int(hit)][1]
                break
        named = near_poi is not None and near_poi.intersects(geometry)
        if owner is None and not (named or building_is_protected(properties)):
            continue
        if owner is None:
            name = properties.get("name_en") or properties.get("name")
            owner = Place(properties.get("source_id", f"building/{len(places)}"), name)
            places.append(owner)
        height = float(properties.get("render_height_m") or 0.0)
        owner.shapes += [(p, height) for p in _polygons(geometry.buffer(MARGIN_M))]
        members[properties.get("source_id", "")] = owner
        kept.append((geometry, properties))
    # Buildings drawn from parts can rise above their outline's height (a 24 m wing on an
    # 8 m outline): cover every part up to its own height too.
    for source_id, pieces in parts_by_building(kept, layers.get("building_parts", [])).items():
        for piece, part in pieces:
            members[source_id].shapes += [
                (p, float(part["height_m"])) for p in _polygons(piece.buffer(MARGIN_M))
            ]
    return places


def protected_shapes(
    layers: dict[str, list[tuple[BaseGeometry, dict[str, Any]]]],
    pois: list[dict[str, Any]],
    bounds: MapBounds,
) -> list[Shape]:
    """Every sensitive place's shapes: world polygons (with margin) and their heights."""
    return [shape for place in sensitive_places(layers, pois, bounds) for shape in place.shapes]


def place_box(
    place: Place, projection: IsoProjection, size: tuple[int, int]
) -> tuple[int, int, int, int] | None:
    """Native-pixel box around a place's swept silhouettes, clamped to the image."""
    us: list[float] = []
    vs: list[float] = []
    for polygon, z in place.shapes:
        for x, y, *_ in polygon.exterior.coords:
            for height in (0.0, z):
                u, v = projection.world_to_native(x, y, height)
                us.append(u)
                vs.append(v)
    if not us:
        return None
    left, top = max(int(min(us)) - 2, 0), max(int(min(vs)) - 2, 0)
    right, bottom = min(int(max(us)) + 3, size[0]), min(int(max(vs)) + 3, size[1])
    return (left, top, right, bottom) if right > left and bottom > top else None


def _share(hsv: np.ndarray, mask: np.ndarray, spec: tuple[tuple[int, int], int, int]) -> float:
    (low, high), saturation, value = spec
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    hit = (h >= low) & (h <= high) & (s >= saturation) & (v >= value) & mask
    return float(hit.sum()) / max(int(mask.sum()), 1)


def recognisable(drawing: Image.Image, painted: Image.Image, mask: np.ndarray) -> dict[str, Any]:
    """Whether the AI kept a place recognisable: its gilding and temple roofs, and its outlines."""
    from .drift import EDGE_TOLERANCE_PX, dilate, luminance_edges

    before = np.asarray(drawing.convert("HSV"))
    after = np.asarray(painted.convert("HSV"))
    result: dict[str, Any] = {}
    failed = []
    for name, spec in (("gold", GOLD), ("temple_roof", TEMPLE_ROOF)):
        drawn = _share(before, mask, spec)
        if drawn < MIN_SIGNATURE:
            continue
        kept = _share(after, mask, spec) / drawn
        result[f"{name}_retained"] = round(kept, 3)
        if kept < MIN_RETAINED:
            failed.append(name)
    edges = luminance_edges(drawing) & mask
    recall = float(
        (edges & dilate(luminance_edges(painted), EDGE_TOLERANCE_PX)).sum() / max(edges.sum(), 1)
    )
    result["edge_recall"] = round(recall, 3)
    if edges.sum() > 0 and recall < MIN_PLACE_RECALL:
        failed.append("outlines")
    result["failed"] = failed
    result["recognisable"] = not failed
    return result


def load_overrides(curated_dir: Path) -> dict[str, set[str]]:
    """data/curated/<area>/ai_places.json: {"protect": [source ids], "allow": [source ids]}."""
    path = curated_dir / "ai_places.json"
    if not path.exists():
        return {"protect": set(), "allow": set()}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {key: set(data.get(key, [])) for key in ("protect", "allow")}


def load_pois(*paths: Path) -> list[dict[str, Any]]:
    pois: list[dict[str, Any]] = []
    for path in paths:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            pois += data["pois"] if isinstance(data, dict) else data
    return pois


def rasterize(
    shapes: list[Shape], projection: IsoProjection, box: tuple[int, int, int, int]
) -> np.ndarray:
    """Coverage in [0, 1] over `box` (native pixels): silhouettes swept from ground to height,
    softened over FEATHER_PX so the AI fades into the drawing instead of stopping at a hard edge.
    """
    left, top, right, bottom = box
    pad = FEATHER_PX * 2
    image = Image.new("L", (right - left + 2 * pad, bottom - top + 2 * pad), 0)
    draw = ImageDraw.Draw(image)
    ox, oy = left - pad, top - pad

    def ring(coords: list[tuple[float, ...]], z: float) -> list[tuple[float, float]]:
        points = []
        for x, y, *_ in coords:
            u, v = projection.world_to_native(x, y, z)
            points.append((u - ox, v - oy))
        return points

    width, height = image.size
    for polygon, z in shapes:
        coords = list(polygon.exterior.coords)
        base = ring(coords, 0.0)
        xs = [u for u, _ in base]
        ys = [v for _, v in base]
        lift = projection.world_to_native(0, 0, z)[1] - projection.world_to_native(0, 0, 0)[1]
        if max(xs) < 0 or min(xs) > width or min(ys) + min(lift, 0) > height or max(ys) < 0:
            continue
        draw.polygon(base, fill=255)
        if z > 0:
            raised = ring(coords, z)
            draw.polygon(raised, fill=255)
            for index in range(len(base) - 1):
                draw.polygon(
                    [base[index], base[index + 1], raised[index + 1], raised[index]], fill=255
                )
    softened = image.filter(ImageFilter.BoxBlur(FEATHER_PX))
    mask = np.asarray(softened, dtype=np.float32)[pad:-pad, pad:-pad] / 255.0
    # Keep full protection over the shapes themselves; only fade outwards.
    hard = np.asarray(image, dtype=np.float32)[pad:-pad, pad:-pad] / 255.0
    return np.maximum(mask, hard)


def places_for_area(bounds: MapBounds, processed_dir: Path, curated_dir: Path) -> list[Place]:
    from .render import load_layers

    layers = load_layers(processed_dir, bounds)
    pois = load_pois(processed_dir / "pois.json", curated_dir / "pois.json")
    return sensitive_places(layers, pois, bounds)


def for_area(bounds: MapBounds, processed_dir: Path, curated_dir: Path) -> list[Shape]:
    places = places_for_area(bounds, processed_dir, curated_dir)
    return [shape for place in places for shape in place.shapes]
