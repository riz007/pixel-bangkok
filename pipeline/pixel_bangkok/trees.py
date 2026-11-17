"""Stage 3 (enrich): tree symbols from OSM tree nodes and a canopy-height raster.

Canopy trees are not individual surveyed trees. A jittered grid (fixed seed)
is sampled against the canopy raster; points on canopy at least
`min_canopy_height_m` tall become tree symbols whose height is the sampled
canopy height. Points on buildings or water are dropped.

Output: data/processed/<area>/trees.enriched.geojson (WGS84 lon/lat).
"""

from __future__ import annotations

import logging
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
import shapely
from shapely.geometry import Point
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from . import rasters
from .config import AreaConfig, RenderConfig, TreeConfig
from .crs import MapBounds
from .geojson_io import feature, read_feature_collection, world_geometries, write_feature_collection

log = logging.getLogger(__name__)

BUILDING_CLEARANCE_M = 0.5


def crown_radius(height_m: float, config: TreeConfig) -> float:
    radius = height_m * config.crown_radius_per_metre
    return round(min(max(radius, config.min_crown_radius_m), config.max_crown_radius_m), 2)


def candidate_points(bounds: MapBounds, spacing_m: float, seed: int) -> np.ndarray:
    columns = int(bounds.width_m // spacing_m)
    rows = int(bounds.height_m // spacing_m)
    xs, ys = np.meshgrid(
        (np.arange(columns) + 0.5) * spacing_m, (np.arange(rows) + 0.5) * spacing_m
    )
    rng = np.random.default_rng(seed)
    jitter = rng.uniform(-0.35, 0.35, size=(2, rows, columns)) * spacing_m
    return np.column_stack(((xs + jitter[0]).ravel(), (ys + jitter[1]).ravel()))


def place_canopy_trees(
    canopy: rasters.RasterLayer,
    bounds: MapBounds,
    blocked: BaseGeometry,
    config: TreeConfig,
    seed: int,
) -> list[tuple[Point, float]]:
    shapely.prepare(blocked)
    placed: list[tuple[Point, float]] = []
    for x, y in candidate_points(bounds, config.spacing_m, seed):
        height = rasters.sample_point(canopy, "canopy_height", x, y, bounds)
        if height == rasters.NODATA or height < config.min_canopy_height_m:
            continue
        point = Point(float(x), float(y))
        if blocked.intersects(point):
            continue
        placed.append((point, round(height, 2)))
    return placed


def _blocked_area(processed_dir: Path, bounds: MapBounds) -> BaseGeometry:
    shapes: list[BaseGeometry] = []
    for geometry, _ in world_geometries(processed_dir / "buildings.geojson", bounds):
        shapes.append(geometry.buffer(BUILDING_CLEARANCE_M))
    for geometry, properties in world_geometries(processed_dir / "water.geojson", bounds):
        width = properties.get("width_m")
        shapes.append(geometry.buffer(width / 2) if width else geometry)
    return unary_union(shapes)


def run(area: AreaConfig, render: RenderConfig, raw_dir: Path, processed_dir: Path) -> Path:
    config = render.trees
    bounds = MapBounds.from_area(area)
    osm = read_feature_collection(processed_dir / "trees.geojson")
    features: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    for geometry, properties in world_geometries(processed_dir / "trees.geojson", bounds):
        features.append(
            feature(
                geometry,
                {
                    "source_id": properties["source_id"],
                    "source": properties["source"],
                    "height_m": config.default_height_m,
                    "crown_radius_m": config.default_crown_radius_m,
                    "height_provenance": "unknown",
                },
                bounds,
            )
        )
        counts["osm"] += 1

    canopy_path = raw_dir / "tree_canopy.tif"
    metadata = dict(osm["metadata"])
    if area.tree_canopy is not None and canopy_path.exists():
        canopy = rasters.read_layer(canopy_path)
        blocked = _blocked_area(processed_dir, bounds)
        for index, (point, height) in enumerate(
            place_canopy_trees(canopy, bounds, blocked, config, render.seed)
        ):
            features.append(
                feature(
                    point,
                    {
                        "source_id": f"canopy/{index}",
                        "source": area.tree_canopy.dataset,
                        "height_m": height,
                        "crown_radius_m": crown_radius(height, config),
                        "height_provenance": "estimated",
                    },
                    bounds,
                )
            )
            counts["canopy"] += 1
        metadata["canopy"] = {
            "dataset": area.tree_canopy.dataset,
            "licence": area.tree_canopy.licence,
            "note": "symbols placed on a jittered grid where modelled canopy is tall enough; "
            "not individual surveyed trees",
            "spacing_m": config.spacing_m,
            "seed": render.seed,
        }
    elif area.tree_canopy is not None:
        log.warning("%s missing; run extract to add canopy trees", canopy_path)
    metadata["tree_counts"] = dict(sorted(counts.items()))
    output = processed_dir / "trees.enriched.geojson"
    write_feature_collection(output, features, metadata)
    log.info("tree symbols: %s -> %s", dict(counts), output)
    return output
