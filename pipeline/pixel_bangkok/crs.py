"""Geographic <-> local world coordinates.

Boundaries:
- geographic: WGS84 (EPSG:4326), axis order (longitude, latitude), degrees.
- projected: the area's configured CRS (EPSG:32647 for Bangkok), (easting, northing), metres.
- world: projected coordinates relative to the south-west corner of the area
  rectangle, (x east, y north), metres.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property

import numpy as np
import shapely
from pyproj import Transformer
from shapely.geometry.base import BaseGeometry

from .config import AreaConfig

WGS84 = "EPSG:4326"


@dataclass(frozen=True)
class MapBounds:
    crs: str
    origin_easting: float
    origin_northing: float
    width_m: float
    height_m: float

    @cached_property
    def _to_projected(self) -> Transformer:
        return Transformer.from_crs(WGS84, self.crs, always_xy=True)

    @cached_property
    def _to_geographic(self) -> Transformer:
        return Transformer.from_crs(self.crs, WGS84, always_xy=True)

    @classmethod
    def from_area(cls, area: AreaConfig) -> MapBounds:
        to_projected = Transformer.from_crs(WGS84, area.crs, always_xy=True)
        easting, northing = to_projected.transform(area.center_lon, area.center_lat)
        return cls(
            crs=area.crs,
            origin_easting=round(easting - area.width_m / 2, 3),
            origin_northing=round(northing - area.height_m / 2, 3),
            width_m=area.width_m,
            height_m=area.height_m,
        )

    def lonlat_to_world(self, lon: float, lat: float) -> tuple[float, float]:
        easting, northing = self._to_projected.transform(lon, lat)
        return easting - self.origin_easting, northing - self.origin_northing

    def world_to_lonlat(self, x: float, y: float) -> tuple[float, float]:
        return self._to_geographic.transform(x + self.origin_easting, y + self.origin_northing)

    def geometry_to_world(self, geometry: BaseGeometry) -> BaseGeometry:
        def convert(coords: np.ndarray) -> np.ndarray:
            easting, northing = self._to_projected.transform(coords[:, 0], coords[:, 1])
            return np.column_stack((easting - self.origin_easting, northing - self.origin_northing))

        return shapely.transform(geometry, convert)

    def geometry_to_lonlat(self, geometry: BaseGeometry) -> BaseGeometry:
        def convert(coords: np.ndarray) -> np.ndarray:
            lon, lat = self._to_geographic.transform(
                coords[:, 0] + self.origin_easting, coords[:, 1] + self.origin_northing
            )
            return np.column_stack((lon, lat))

        return shapely.transform(geometry, convert)

    def contains_world(self, x: float, y: float) -> bool:
        return 0 <= x <= self.width_m and 0 <= y <= self.height_m

    def geographic_bbox(self, buffer_m: float = 0.0) -> tuple[float, float, float, float]:
        """Return (south, west, north, east) in degrees enclosing the area rectangle."""
        corners = [
            self.world_to_lonlat(x, y)
            for x in (-buffer_m, self.width_m + buffer_m)
            for y in (-buffer_m, self.height_m + buffer_m)
        ]
        lons = [c[0] for c in corners]
        lats = [c[1] for c in corners]
        return min(lats), min(lons), max(lats), max(lons)

    def to_dict(self) -> dict[str, object]:
        south, west, north, east = self.geographic_bbox()
        return {
            "crs": self.crs,
            "origin_easting": self.origin_easting,
            "origin_northing": self.origin_northing,
            "width_m": self.width_m,
            "height_m": self.height_m,
            "geographic_bbox": {"south": south, "west": west, "north": north, "east": east},
        }
