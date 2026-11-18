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
FIT_SAMPLES = 21


def _terms(u: np.ndarray, v: np.ndarray) -> np.ndarray:
    return np.stack([np.ones_like(u), u, v, u * u, u * v, v * v], axis=-1)


def _fit(
    source: np.ndarray, target: np.ndarray, origin: tuple[float, float]
) -> tuple[list[float], list[float], np.ndarray]:
    terms = _terms(source[:, 0] - origin[0], source[:, 1] - origin[1])
    first, *_ = np.linalg.lstsq(terms, target[:, 0], rcond=None)
    second, *_ = np.linalg.lstsq(terms, target[:, 1], rcond=None)
    predicted = np.stack([terms @ first, terms @ second], axis=-1)
    return [float(c) for c in first], [float(c) for c in second], predicted


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

    def browser_transforms(self) -> dict[str, object]:
        """Quadratic fits of lon/lat <-> world for clients without a projection library.

        Each output is c0 + c1*u + c2*v + c3*u^2 + c4*u*v + c5*v^2 with (u, v) the input minus
        `origin`; `max_error_m` is the worst residual on a 21 x 21 grid over the area.
        """
        xs, ys = np.meshgrid(
            np.linspace(0, self.width_m, FIT_SAMPLES), np.linspace(0, self.height_m, FIT_SAMPLES)
        )
        world = np.stack([xs.ravel(), ys.ravel()], axis=-1)
        lons, lats = self._to_geographic.transform(
            world[:, 0] + self.origin_easting, world[:, 1] + self.origin_northing
        )
        lonlat = np.stack([np.asarray(lons), np.asarray(lats)], axis=-1)
        centre_lonlat = self.world_to_lonlat(self.width_m / 2, self.height_m / 2)
        x_coefficients, y_coefficients, predicted_world = _fit(lonlat, world, centre_lonlat)
        centre_world = (self.width_m / 2, self.height_m / 2)
        lon_coefficients, lat_coefficients, predicted_lonlat = _fit(world, lonlat, centre_world)
        back = np.array(
            self._to_projected.transform(predicted_lonlat[:, 0], predicted_lonlat[:, 1])
        ).T - np.array([self.origin_easting, self.origin_northing])
        return {
            "lonlat_to_world": {
                "origin": list(centre_lonlat),
                "x": x_coefficients,
                "y": y_coefficients,
                "max_error_m": float(np.max(np.hypot(*(predicted_world - world).T))),
            },
            "world_to_lonlat": {
                "origin": list(centre_world),
                "lon": lon_coefficients,
                "lat": lat_coefficients,
                "max_error_m": float(np.max(np.hypot(*(back - world).T))),
            },
        }

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
