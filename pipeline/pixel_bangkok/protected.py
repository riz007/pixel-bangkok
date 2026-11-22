"""Places the AI repaint must never touch: worship, palaces, government, military, monuments.

These always show the procedural drawing, so the AI can never restyle a temple, the Grand Palace
or a mosque in a foreign idiom. Shapes come from the processed OSM layers (world metres) and the
POI files, and are drawn in native image pixels with the render's own projection. Each protected
building is covered by its whole silhouette (walls and roof, not only its footprint), plus a
margin, and every building inside a protected ground area (a temple or palace compound) is
protected too.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from shapely.geometry import MultiPolygon, Point, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union
from shapely.prepared import prep

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


def protected_shapes(
    layers: dict[str, list[tuple[BaseGeometry, dict[str, Any]]]],
    pois: list[dict[str, Any]],
    bounds: MapBounds,
) -> list[Shape]:
    """World-space polygons (with margin) and the height to sweep each one up to."""
    shapes: list[Shape] = []
    grounds = [
        geometry
        for geometry, properties in layers.get("ground", [])
        if properties.get("category") in GROUND_CATEGORIES
    ]
    for ground in grounds:
        shapes += [(p, 0.0) for p in _polygons(ground.buffer(MARGIN_M))]
    compound = prep(unary_union(grounds)) if grounds else None
    points = [
        Point(*bounds.lonlat_to_world(float(poi["lon"]), float(poi["lat"])))
        for poi in pois
        if poi.get("category") in POI_CATEGORIES or poi.get("id") in POI_IDS
    ]
    near_poi = prep(unary_union([point.buffer(POI_SNAP_M) for point in points])) if points else None
    for geometry, properties in layers.get("buildings", []):
        inside = compound is not None and compound.contains(geometry.representative_point())
        named = near_poi is not None and near_poi.intersects(geometry)
        if inside or named or building_is_protected(properties):
            height = float(properties.get("render_height_m") or 0.0)
            shapes += [(p, height) for p in _polygons(geometry.buffer(MARGIN_M))]
    return shapes


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


def for_area(bounds: MapBounds, processed_dir: Path, curated_dir: Path) -> list[Shape]:
    from .render import load_layers

    layers = load_layers(processed_dir, bounds)
    pois = load_pois(processed_dir / "pois.json", curated_dir / "pois.json")
    return protected_shapes(layers, pois, bounds)
