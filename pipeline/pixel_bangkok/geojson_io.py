from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from shapely.geometry import mapping, shape
from shapely.geometry.base import BaseGeometry

from .crs import WGS84, MapBounds

COORDINATE_DECIMALS = 7


def _round_coordinates(value: Any) -> Any:
    if isinstance(value, (list, tuple)):
        return [_round_coordinates(item) for item in value]
    return round(value, COORDINATE_DECIMALS)


def feature(geometry_world: BaseGeometry, properties: dict[str, Any], bounds: MapBounds) -> dict:
    geographic = bounds.geometry_to_lonlat(geometry_world)
    geometry = mapping(geographic)
    return {
        "type": "Feature",
        "properties": properties,
        "geometry": {
            "type": geometry["type"],
            "coordinates": _round_coordinates(geometry["coordinates"]),
        },
    }


def write_feature_collection(path: Path, features: list[dict], metadata: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    collection = {
        "type": "FeatureCollection",
        "metadata": {**metadata, "crs": WGS84, "axis_order": "longitude, latitude"},
        "features": features,
    }
    path.write_text(json.dumps(collection, ensure_ascii=False), encoding="utf-8")


def read_feature_collection(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"{path} not found; run the earlier pipeline stages first")
    collection = json.loads(path.read_text(encoding="utf-8"))
    if collection.get("type") != "FeatureCollection":
        raise ValueError(f"{path} is not a GeoJSON FeatureCollection")
    return collection


def world_geometries(path: Path, bounds: MapBounds) -> list[tuple[BaseGeometry, dict[str, Any]]]:
    collection = read_feature_collection(path)
    return [
        (bounds.geometry_to_world(shape(item["geometry"])), item["properties"])
        for item in collection["features"]
    ]
