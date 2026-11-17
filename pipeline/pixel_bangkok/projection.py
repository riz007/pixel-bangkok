"""World -> image transform. The only place this projection is defined.

World coordinates are (x east, y north, z up) in metres relative to the area's
south-west corner. Image coordinates are pixels, origin top-left, y down.

The camera is orthographic. `azimuth_deg` is the compass bearing (clockwise
from north) that points "up" the screen; `elevation_deg` is the camera's angle
above the horizon. Native pixels are what the renderer draws; master pixels are
native pixels multiplied by the integer `upscale`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .config import RenderConfig
from .crs import MapBounds


@dataclass(frozen=True)
class IsoProjection:
    ax: float
    ay: float
    bx: float
    by: float
    bz: float
    tx: float
    ty: float
    native_width: int
    native_height: int
    upscale: int

    @classmethod
    def create(cls, bounds: MapBounds, render: RenderConfig) -> IsoProjection:
        azimuth = math.radians(render.camera_azimuth_deg)
        elevation = math.radians(render.camera_elevation_deg)
        ppm = render.pixels_per_metre
        ax = math.cos(azimuth) * ppm
        ay = -math.sin(azimuth) * ppm
        bx = -math.sin(azimuth) * math.sin(elevation) * ppm
        by = -math.cos(azimuth) * math.sin(elevation) * ppm
        bz = -math.cos(elevation) * ppm
        corners = [
            (0.0, 0.0),
            (bounds.width_m, 0.0),
            (0.0, bounds.height_m),
            (bounds.width_m, bounds.height_m),
        ]
        sx = [ax * x + ay * y for x, y in corners]
        sy = [bx * x + by * y for x, y in corners]
        top_margin = math.ceil(-bz * render.max_height_m)
        tx = float(-math.floor(min(sx)))
        ty = float(-math.floor(min(sy)) + top_margin)
        return cls(
            ax=ax,
            ay=ay,
            bx=bx,
            by=by,
            bz=bz,
            tx=tx,
            ty=ty,
            native_width=math.ceil(max(sx) + tx) + 1,
            native_height=math.ceil(max(sy) + ty) + 1,
            upscale=render.upscale,
        )

    @property
    def master_width(self) -> int:
        return self.native_width * self.upscale

    @property
    def master_height(self) -> int:
        return self.native_height * self.upscale

    def world_to_native(self, x: float, y: float, z: float = 0.0) -> tuple[float, float]:
        return (
            self.ax * x + self.ay * y + self.tx,
            self.bx * x + self.by * y + self.bz * z + self.ty,
        )

    def world_to_master(self, x: float, y: float, z: float = 0.0) -> tuple[float, float]:
        px, py = self.world_to_native(x, y, z)
        return px * self.upscale, py * self.upscale

    def depth(self, x: float, y: float) -> float:
        """Distance from the camera along the ground; larger is further away."""
        return -(self.bx * x + self.by * y)

    def screen_ground_matrix(self) -> list[float]:
        """Shapely affine matrix mapping world (x, y) to (screen x, depth)."""
        return [self.ax, self.ay, -self.bx, -self.by, 0.0, 0.0]

    def master_matrix(self) -> dict[str, list[float]]:
        s = self.upscale
        return {
            "px": [self.ax * s, self.ay * s, 0.0, self.tx * s],
            "py": [self.bx * s, self.by * s, self.bz * s, self.ty * s],
        }
