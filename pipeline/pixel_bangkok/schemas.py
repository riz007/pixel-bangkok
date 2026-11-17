"""Typed records exchanged between pipeline stages.

Processed datasets are GeoJSON FeatureCollections in WGS84 (EPSG:4326),
coordinates in (longitude, latitude) order, with these property shapes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, NotRequired, TypedDict

HeightProvenance = Literal["source", "estimated", "manual", "unknown"]
WidthProvenance = Literal["source", "estimated"]
RoofShape = Literal["flat", "spire", "gabled", "chedi", "prang"]


class BaseProperties(TypedDict):
    source_id: str
    source: str
    name: str | None
    name_en: str | None
    name_th: str | None
    clipped: bool


class BuildingFeature(BaseProperties):
    category: str
    is_temple: bool
    is_tower: bool
    tower_type: NotRequired[str | None]
    source_height: str | None
    source_levels: str | None
    raster_height_m: NotRequired[float | None]
    render_height_m: NotRequired[float]
    height_provenance: NotRequired[HeightProvenance]
    height_source: NotRequired[str | None]
    height_note: NotRequired[str | None]
    roof_shape: NotRequired[RoofShape]


class RoadFeature(BaseProperties):
    category: str
    bridge: bool
    width_m: float
    width_provenance: WidthProvenance


class WaterFeature(BaseProperties):
    category: str
    width_m: float | None
    width_provenance: WidthProvenance | None


class GreenSpaceFeature(BaseProperties):
    category: str


class TreeFeature(TypedDict):
    source_id: str
    source: str
    height_m: float
    crown_radius_m: float
    height_provenance: HeightProvenance


POI_CATEGORIES = ("temple", "landmark", "pier", "historic", "market", "neighbourhood")


class SchemaError(ValueError):
    pass


@dataclass(frozen=True)
class PointOfInterest:
    id: str
    name_en: str
    category: str
    lon: float
    lat: float
    description: str
    name_th: str | None = None
    aliases: tuple[str, ...] = field(default_factory=tuple)
    source: str | None = None
    source_url: str | None = None
    icon: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PointOfInterest:
        for key in ("id", "name_en", "category", "lon", "lat", "description"):
            if key not in data:
                raise SchemaError(f"POI is missing '{key}': {data.get('id', data)}")
        if data["category"] not in POI_CATEGORIES:
            raise SchemaError(f"POI {data['id']} has unknown category '{data['category']}'")
        lon, lat = float(data["lon"]), float(data["lat"])
        if not (-180 <= lon <= 180 and -90 <= lat <= 90):
            raise SchemaError(f"POI {data['id']} coordinates must be lon/lat degrees")
        return cls(
            id=str(data["id"]),
            name_en=str(data["name_en"]),
            category=str(data["category"]),
            lon=lon,
            lat=lat,
            description=str(data["description"]),
            name_th=data.get("name_th"),
            aliases=tuple(data.get("aliases", ())),
            source=data.get("source"),
            source_url=data.get("source_url"),
            icon=data.get("icon"),
        )
