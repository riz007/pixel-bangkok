"""Stage 4: deterministic procedural isometric render.

Input: processed GeoJSON layers (WGS84) for one area.
Output: build/<area>/render.png at native resolution plus one PNG per layer in
build/<area>/layers/. This image is the authoritative geometry reference.

Buildings and trees share one back-to-front order. Each is drawn into its own
layer; a building also clears the vegetation-layer pixels it covers, so trees
behind it stay hidden even though vegetation composites above buildings.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from PIL import Image, ImageDraw
from shapely.affinity import affine_transform, scale, translate
from shapely.geometry import LineString, MultiLineString, MultiPolygon, Point, Polygon, box
from shapely.geometry.base import BaseGeometry
from shapely.geometry.polygon import orient
from shapely.ops import substring, unary_union

from .config import AreaConfig, RenderConfig
from .crs import MapBounds
from .depthsort import back_to_front
from .geojson_io import world_geometries
from .projection import IsoProjection

log = logging.getLogger(__name__)

LAYER_ORDER = ("terrain", "water", "green", "roads", "shadows", "buildings", "vegetation")
PATH_CATEGORIES = {"footway", "path", "steps", "pedestrian", "cycleway"}
MAJOR_CATEGORIES = {"motorway", "trunk", "primary", "secondary", "tertiary"}
WALL_LIGHT_THRESHOLD = 0.1
GABLE_MIN_RECTANGULARITY = 0.8
GABLE_MIN_WIDTH_M = 4.0
GABLE_EAVE_FRACTION = 0.55
GABLE_OVERHANG = 1.08
WINDOW_TOP_CLEARANCE_M = 0.2
SHADE_FACTOR = 0.62
CONTACT_SHADOW_M = 0.9
FOAM_INSET_M = 1.0
ROOF_TILE_SPACING_M = 1.0
PRANG_TERRACES = ((1.0, 0.0, 0.08), (0.84, 0.08, 0.16), (0.68, 0.16, 0.24))
PRANG_TOWER = (0.24, 0.86, 9)
CHEDI_PLINTHS = ((1.0, 0.0, 0.1), (0.9, 0.1, 0.16))
CHEDI_BELL = (0.16, 0.5, 6)
CHEDI_HARMIKA = (0.3, 0.5, 0.56)
TREE_FOOTPRINT_FRACTION = 0.5
TRANSPARENT = (0, 0, 0, 0)

Color = tuple[int, int, int, int]
XY = tuple[float, float]
XYZ = tuple[float, float, float]


def parse_color(value: str) -> Color:
    text = value.lstrip("#")
    if len(text) not in (6, 8):
        raise ValueError(f"palette colour must be #rrggbb or #rrggbbaa: {value}")
    channels = [int(text[i : i + 2], 16) for i in range(0, len(text), 2)]
    if len(channels) == 3:
        channels.append(255)
    return channels[0], channels[1], channels[2], channels[3]


def _polygons(geometry: BaseGeometry) -> list[Polygon]:
    if isinstance(geometry, Polygon):
        return [geometry]
    if isinstance(geometry, MultiPolygon):
        return list(geometry.geoms)
    return [part for part in getattr(geometry, "geoms", []) if isinstance(part, Polygon)]


def _lines(geometry: BaseGeometry) -> list[LineString]:
    if isinstance(geometry, LineString):
        return [geometry]
    if isinstance(geometry, MultiLineString):
        return list(geometry.geoms)
    return []


@dataclass(frozen=True)
class Primitive:
    kind: Literal["polygon", "line", "area"]
    fill: str | None
    outline: str | None = None
    points: tuple[XY, ...] = ()
    geometry: BaseGeometry | None = None
    z: float = 0.0


class SceneRenderer:
    def __init__(self, bounds: MapBounds, render: RenderConfig) -> None:
        self.bounds = bounds
        self.config = render
        self.projection = IsoProjection.create(bounds, render)
        self.size = (self.projection.native_width, self.projection.native_height)
        self.palette = {name: parse_color(value) for name, value in render.palette.items()}
        camera = math.radians(render.camera_azimuth_deg)
        elevation = math.radians(render.camera_elevation_deg)
        self.toward_camera = (-math.sin(camera), -math.cos(camera))
        self.toward_camera_3d = (
            self.toward_camera[0] * math.cos(elevation),
            self.toward_camera[1] * math.cos(elevation),
            math.sin(elevation),
        )
        self.sin_elevation = math.sin(elevation)
        self.cos_elevation = math.cos(elevation)
        light = math.radians(render.light_azimuth_deg)
        self.toward_light = (math.sin(light), math.cos(light))
        origin = self.projection.world_to_native(0, 0, 0)
        lit = self.projection.world_to_native(self.toward_light[0], self.toward_light[1], 0.6)
        length = math.hypot(lit[0] - origin[0], lit[1] - origin[1]) or 1.0
        self.light_on_screen = ((lit[0] - origin[0]) / length, (lit[1] - origin[1]) / length)
        self._shades: dict[str, Color] = {}

    def color(self, name: str) -> Color:
        """Palette colour; `shade:<name>` is a darker tone of <name> for pixel-art edges."""
        if not name.startswith("shade:"):
            return self.palette[name]
        if name not in self._shades:
            r, g, b, a = self.palette[name.removeprefix("shade:")]
            self._shades[name] = (
                int(r * SHADE_FACTOR),
                int(g * SHADE_FACTOR),
                int(b * SHADE_FACTOR),
                a,
            )
        return self._shades[name]

    def _blank(self) -> Image.Image:
        return Image.new("RGBA", self.size, TRANSPARENT)

    def _ring(self, coords: Any, z: float = 0.0) -> list[XY]:
        return [self.projection.world_to_native(x, y, z) for x, y in coords]

    def _mask(self, geometry: BaseGeometry, z: float = 0.0) -> Image.Image:
        mask = Image.new("L", self.size, 0)
        draw = ImageDraw.Draw(mask)
        for polygon in _polygons(geometry):
            draw.polygon(self._ring(polygon.exterior.coords, z), fill=255)
            for interior in polygon.interiors:
                draw.polygon(self._ring(interior.coords, z), fill=0)
        return mask

    def _fill(self, layer: Image.Image, geometry: BaseGeometry, color: Color) -> None:
        if geometry.is_empty:
            return
        layer.paste(Image.new("RGBA", self.size, color), (0, 0), self._mask(geometry))

    def _outline(self, layer: Image.Image, geometry: BaseGeometry, color: Color) -> None:
        draw = ImageDraw.Draw(layer)
        for polygon in _polygons(geometry):
            for ring in (polygon.exterior, *polygon.interiors):
                draw.line(self._ring(ring.coords), fill=color, width=1)

    def _clip(self, geometry: BaseGeometry) -> BaseGeometry:
        return geometry.intersection(box(0, 0, self.bounds.width_m, self.bounds.height_m))

    def paint(self, layer: Image.Image, primitives: list[Primitive], erase: bool = False) -> None:
        draw = ImageDraw.Draw(layer)

        def color(name: str | None) -> Color | None:
            if name is None:
                return None
            return TRANSPARENT if erase else self.color(name)

        for primitive in primitives:
            if primitive.kind == "polygon":
                draw.polygon(
                    list(primitive.points),
                    fill=color(primitive.fill),
                    outline=None if erase else color(primitive.outline),
                )
            elif primitive.kind == "line":
                if not erase:
                    draw.line(list(primitive.points), fill=color(primitive.outline), width=1)
            elif primitive.geometry is not None and not primitive.geometry.is_empty:
                fill = color(primitive.fill)
                if fill is not None:
                    layer.paste(
                        Image.new("RGBA", self.size, fill),
                        (0, 0),
                        self._mask(primitive.geometry, primitive.z),
                    )
                    draw = ImageDraw.Draw(layer)

    def terrain(self) -> Image.Image:
        layer = self._blank()
        area = box(0, 0, self.bounds.width_m, self.bounds.height_m)
        self._fill(layer, area, self.palette["terrain"])
        self._outline(layer, area, self.palette["terrain_edge"])
        return layer

    def water(self, features: list[tuple[BaseGeometry, dict]]) -> Image.Image:
        layer = self._blank()
        shapes = [
            geometry.buffer(properties["width_m"] / 2, cap_style="flat")
            if properties.get("width_m")
            else geometry
            for geometry, properties in features
        ]
        merged = self._clip(unary_union(shapes))
        self._fill(layer, merged, self.palette["water"])
        self._outline(layer, merged, self.palette["water_edge"])
        area_edge = box(0, 0, self.bounds.width_m, self.bounds.height_m).exterior.buffer(
            FOAM_INSET_M * 1.5
        )
        foam = merged.buffer(-FOAM_INSET_M).boundary.difference(area_edge)
        draw = ImageDraw.Draw(layer)
        for line in sorted(_lines(foam), key=lambda item: item.wkb):
            draw.line(self._ring(line.coords), fill=self.palette["foam"], width=1)
        return layer

    def green(self, features: list[tuple[BaseGeometry, dict]]) -> Image.Image:
        layer = self._blank()
        self._fill(layer, unary_union([g for g, _ in features]), self.palette["green"])
        return layer

    def roads(self, features: list[tuple[BaseGeometry, dict]]) -> Image.Image:
        layer = self._blank()
        groups: dict[str, list[BaseGeometry]] = {"pier": [], "path": [], "road": [], "major": []}
        centre_lines: list[LineString] = []
        style = self.config.roads
        for geometry, properties in features:
            category = properties["category"]
            is_line = geometry.geom_type in {"LineString", "MultiLineString"}
            if is_line:
                if (
                    category not in PATH_CATEGORIES
                    and category != "pier"
                    and properties["width_m"] >= style.marking_min_width_m
                ):
                    centre_lines.extend(_lines(geometry))
                geometry = geometry.buffer(properties["width_m"] / 2, cap_style="round")
            if category == "pier":
                groups["pier"].append(geometry)
            elif category in PATH_CATEGORIES:
                groups["path"].append(geometry)
            elif category in MAJOR_CATEGORIES:
                groups["major"].append(geometry)
            else:
                groups["road"].append(geometry)
        colors = {"pier": "pier", "path": "path", "road": "road", "major": "road_major"}
        carriageway = self._clip(unary_union(groups["road"] + groups["major"]))
        for group in ("pier", "path"):
            self._fill(layer, self._clip(unary_union(groups[group])), self.palette[colors[group]])
        self._fill(layer, carriageway, self.palette["road"])
        self._fill(layer, self._clip(unary_union(groups["major"])), self.palette["road_major"])
        self._outline(layer, carriageway, self.palette["road_edge"])
        draw = ImageDraw.Draw(layer)
        period = style.dash_m + style.gap_m
        for line in sorted(centre_lines, key=lambda item: item.wkb):
            start = style.gap_m / 2
            while start < line.length:
                dash = substring(line, start, min(start + style.dash_m, line.length))
                if dash.length > 0:
                    draw.line(self._ring(dash.coords), fill=self.palette["road_marking"], width=1)
                start += period
        return layer

    def _tree_crown_centre(self, properties: dict) -> float:
        radius = properties["crown_radius_m"]
        return max(properties["height_m"] - radius, radius)

    def shadows(
        self,
        buildings: list[tuple[BaseGeometry, dict]],
        trees: list[tuple[BaseGeometry, dict]],
    ) -> Image.Image:
        swept: list[BaseGeometry] = []
        per_metre = self.config.shadow_length_per_metre
        away = (-self.toward_light[0], -self.toward_light[1])
        for geometry, properties in buildings:
            length = properties["render_height_m"] * per_metre
            dx, dy = away[0] * length, away[1] * length
            for polygon in _polygons(geometry):
                coords = list(polygon.exterior.coords)
                quads = [
                    Polygon([a, b, (b[0] + dx, b[1] + dy), (a[0] + dx, a[1] + dy)])
                    for a, b in zip(coords, coords[1:], strict=False)
                ]
                swept.append(
                    unary_union([q.buffer(0) for q in quads] + [translate(polygon, dx, dy)])
                )
        for point, properties in trees:
            length = self._tree_crown_centre(properties) * per_metre
            centre = Point(point.x + away[0] * length, point.y + away[1] * length)
            swept.append(centre.buffer(properties["crown_radius_m"], quad_segs=8))
        layer = self._blank()
        self._fill(layer, self._clip(unary_union(swept)), self.palette["shadow"])
        contact = self._blank()
        footprints = [geometry.buffer(CONTACT_SHADOW_M) for geometry, _ in buildings]
        self._fill(contact, self._clip(unary_union(footprints)), self.palette["contact_shadow"])
        return Image.alpha_composite(layer, contact)

    def _wall_color(self, a: XY, b: XY, temple: bool) -> str:
        nx, ny = b[1] - a[1], a[0] - b[0]
        length = math.hypot(nx, ny) or 1.0
        lit = (nx * self.toward_light[0] + ny * self.toward_light[1]) / length
        tone = "light" if lit > WALL_LIGHT_THRESHOLD else "dark"
        return f"{'temple' if temple else 'building'}_wall_{tone}"

    def _edges(self, polygon: Polygon) -> list[tuple[XY, XY]]:
        edges = []
        for ring in (polygon.exterior, *polygon.interiors):
            coords = list(ring.coords)
            edges.extend(zip(coords, coords[1:], strict=False))
        return sorted(
            edges,
            key=lambda edge: (
                -self.projection.depth((edge[0][0] + edge[1][0]) / 2, (edge[0][1] + edge[1][1]) / 2)
            ),
        )

    def _faces_camera(self, a: XY, b: XY) -> bool:
        nx, ny = b[1] - a[1], a[0] - b[0]
        return nx * self.toward_camera[0] + ny * self.toward_camera[1] > 0

    def _windows(self, a: XY, b: XY, wall_height: float, temple: bool) -> list[Primitive]:
        facade = self.config.facade
        floor = self.config.heights.floor_height_m
        length = math.hypot(b[0] - a[0], b[1] - a[1])
        count = int((length - facade.window_spacing_m / 2) // facade.window_spacing_m)
        if count < 1:
            return []
        ux, uy = (b[0] - a[0]) / length, (b[1] - a[1]) / length
        offset = (length - count * facade.window_spacing_m) / 2
        offset += (facade.window_spacing_m - facade.window_width_m) / 2
        project = self.projection.world_to_native
        fill = "window_temple" if temple else "window"
        primitives = []
        storey = 0
        while True:
            bottom = storey * floor + facade.sill_height_m
            top = bottom + facade.window_height_m
            if top > wall_height - WINDOW_TOP_CLEARANCE_M:
                break
            for index in range(count):
                start = offset + index * facade.window_spacing_m
                end = start + facade.window_width_m
                p0 = (a[0] + ux * start, a[1] + uy * start)
                p1 = (a[0] + ux * end, a[1] + uy * end)
                primitives.append(
                    Primitive(
                        "polygon",
                        fill,
                        points=(
                            project(*p0, bottom),
                            project(*p1, bottom),
                            project(*p1, top),
                            project(*p0, top),
                        ),
                    )
                )
                primitives.append(
                    Primitive(
                        "line", None, "window_light", points=(project(*p0, top), project(*p1, top))
                    )
                )
            storey += 1
        return primitives

    def _walls(self, polygon: Polygon, wall_height: float, temple: bool) -> list[Primitive]:
        project = self.projection.world_to_native
        primitives = []
        for a, b in self._edges(polygon):
            if not self._faces_camera(a, b):
                continue
            quad = (project(*a), project(*b), project(*b, wall_height), project(*a, wall_height))
            fill = self._wall_color(a, b, temple)
            primitives.append(Primitive("polygon", fill, f"shade:{fill}", points=quad))
            primitives.extend(self._windows(a, b, wall_height, temple))
        return primitives

    def _roof_outline(self, polygon: Polygon, height: float) -> list[Primitive]:
        return [
            Primitive("line", None, "outline", points=tuple(self._ring(ring.coords, height)))
            for ring in (polygon.exterior, *polygon.interiors)
        ]

    def prism(self, polygon: Polygon, height: float, temple: bool) -> list[Primitive]:
        primitives = self._walls(polygon, height, temple)
        if temple:
            primitives.append(Primitive("area", "temple_roof", geometry=polygon, z=height))
        else:
            primitives.append(Primitive("area", "building_roof_edge", geometry=polygon, z=height))
            inner = polygon.buffer(-self.config.facade.parapet_m, join_style="mitre")
            if not inner.is_empty:
                primitives.append(Primitive("area", "building_roof", geometry=inner, z=height))
        return primitives + self._roof_outline(polygon, height)

    def spire(self, polygon: Polygon, height: float, temple: bool) -> list[Primitive]:
        project = self.projection.world_to_native
        centroid = polygon.centroid
        apex = project(centroid.x, centroid.y, height)
        primitives = []
        for a, b in self._edges(Polygon(polygon.exterior)):
            fill = self._wall_color(a, b, temple)
            primitives.append(
                Primitive("polygon", fill, f"shade:{fill}", points=(project(*a), project(*b), apex))
            )
        return primitives

    def frustum(
        self,
        low: Polygon,
        z0: float,
        high: Polygon,
        z1: float,
        cap: str | None,
        band: str | None = None,
    ) -> list[Primitive]:
        """Side faces between two similar polygons, then the top cap; back to front."""
        project = self.projection.world_to_native
        lows = list(low.exterior.coords)
        highs = list(high.exterior.coords)
        faces = []
        for index in range(len(lows) - 1):
            a, b = lows[index], lows[index + 1]
            if not self._faces_camera(a, b):
                continue
            c, d = highs[index + 1], highs[index]
            depth = self.projection.depth((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
            faces.append((-depth, a, b, c, d))
        primitives = []
        for _, a, b, c, d in sorted(faces):
            fill = self._wall_color(a, b, temple=True)
            primitives.append(
                Primitive(
                    "polygon",
                    fill,
                    f"shade:{fill}",
                    points=(project(*a, z0), project(*b, z0), project(*c, z1), project(*d, z1)),
                )
            )
            if band is not None:
                primitives.append(
                    Primitive("line", None, band, points=(project(*a, z0), project(*b, z0)))
                )
        if cap is not None and high.area > 0:
            primitives.append(
                Primitive("polygon", cap, f"shade:{cap}", points=tuple(self._ring(highs, z1)))
            )
        return primitives

    def _scaled(self, polygon: Polygon, factor: float) -> Polygon:
        return scale(Polygon(polygon.exterior), factor, factor, origin=polygon.centroid)

    def prang(self, polygon: Polygon, height: float) -> list[Primitive]:
        """Stylised Khmer-style prang: stepped terraces, a bulging tiered tower, a spire."""
        primitives = []
        for factor, bottom, top in PRANG_TERRACES:
            tier = self._scaled(polygon, factor)
            primitives += self.frustum(
                tier, bottom * height, tier, top * height, "temple_wall_light", "temple_trim"
            )
        start, end, segments = PRANG_TOWER

        def radius(t: float) -> float:
            return 0.5 * (1 - 0.75 * t**1.5) * (1 + 0.12 * math.sin(math.pi * t))

        for index in range(segments):
            t0, t1 = index / segments, (index + 1) / segments
            z0 = (start + (end - start) * t0) * height
            z1 = (start + (end - start) * t1) * height
            primitives += self.frustum(
                self._scaled(polygon, radius(t0)),
                z0,
                self._scaled(polygon, radius(t1) * 0.94),
                z1,
                "temple_wall_light",
                "temple_trim" if index % 2 else None,
            )
        tip = self._scaled(polygon, radius(1.0) * 0.8)
        primitives += self.frustum(
            tip, end * height, self._scaled(polygon, 0.01), height, None, "temple_trim"
        )
        return primitives

    def chedi(self, polygon: Polygon, height: float) -> list[Primitive]:
        """Stylised bell-shaped chedi: plinths, bell, harmika, ringed spire with a gilded tip."""
        primitives = []
        for factor, bottom, top in CHEDI_PLINTHS:
            tier = self._scaled(polygon, factor)
            primitives += self.frustum(
                tier, bottom * height, tier, top * height, "temple_wall_light"
            )
        start, end, segments = CHEDI_BELL
        for index in range(segments):
            t0, t1 = index / segments, (index + 1) / segments
            primitives += self.frustum(
                self._scaled(polygon, 0.82 * math.sqrt(1 - (0.85 * t0) ** 2)),
                (start + (end - start) * t0) * height,
                self._scaled(polygon, 0.82 * math.sqrt(1 - (0.85 * t1) ** 2)),
                (start + (end - start) * t1) * height,
                "temple_wall_light",
            )
        factor, bottom, top = CHEDI_HARMIKA
        harmika = self._scaled(polygon, factor)
        primitives += self.frustum(
            harmika, bottom * height, harmika, top * height, "temple_wall_light", "temple_trim"
        )
        rings = 4
        for index in range(rings):
            t0, t1 = index / rings, (index + 1) / rings
            primitives += self.frustum(
                self._scaled(polygon, 0.2 * (1 - t0) + 0.01),
                (top + (1 - top) * t0) * height,
                self._scaled(polygon, 0.2 * (1 - t1) * 0.9 + 0.01),
                (top + (1 - top) * t1) * height,
                "temple_trim" if index == rings - 1 else "temple_wall_light",
                "temple_trim",
            )
        return primitives

    def _front_facing(self, face: list[XYZ], interior: XYZ) -> tuple[bool, float]:
        (x0, y0, z0), (x1, y1, z1), (x2, y2, z2) = face[0], face[1], face[2]
        ux, uy, uz = x1 - x0, y1 - y0, z1 - z0
        vx, vy, vz = x2 - x0, y2 - y0, z2 - z0
        normal = (uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx)
        cx = sum(p[0] for p in face) / len(face) - interior[0]
        cy = sum(p[1] for p in face) / len(face) - interior[1]
        cz = sum(p[2] for p in face) / len(face) - interior[2]
        if normal[0] * cx + normal[1] * cy + normal[2] * cz < 0:
            normal = (-normal[0], -normal[1], -normal[2])
        camera = self.toward_camera_3d
        facing = normal[0] * camera[0] + normal[1] * camera[1] + normal[2] * camera[2] > 0
        lit = normal[0] * self.toward_light[0] + normal[1] * self.toward_light[1]
        return facing, lit

    def gabled(self, polygon: Polygon, height: float, temple: bool) -> list[Primitive] | None:
        rectangle = polygon.minimum_rotated_rectangle
        if not isinstance(rectangle, Polygon) or rectangle.area <= 0:
            return None
        if polygon.area / rectangle.area < GABLE_MIN_RECTANGULARITY:
            return None
        corners = list(orient(rectangle).exterior.coords)[:4]
        sides = [math.dist(corners[i], corners[(i + 1) % 4]) for i in range(4)]
        if min(sides) < GABLE_MIN_WIDTH_M:
            return None
        if sides[1] > sides[0]:
            corners = corners[1:] + corners[:1]
        eaves = scale(Polygon(corners), GABLE_OVERHANG, GABLE_OVERHANG, origin=polygon.centroid)
        p0, p1, p2, p3 = list(eaves.exterior.coords)[:4]
        eave = height * GABLE_EAVE_FRACTION
        ridge_a = ((p3[0] + p0[0]) / 2, (p3[1] + p0[1]) / 2, height)
        ridge_b = ((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2, height)
        e0, e1, e2, e3 = ((*p, eave) for p in (p0, p1, p2, p3))
        centre = polygon.centroid
        interior = (centre.x, centre.y, eave + (height - eave) / 3)
        faces = [
            ([e0, e1, ridge_b, ridge_a], "slope"),
            ([e2, e3, ridge_a, ridge_b], "slope"),
            ([e3, e0, ridge_a], "gable"),
            ([e1, e2, ridge_b], "gable"),
        ]
        project = self.projection.world_to_native
        primitives = self._walls(polygon, eave, temple)
        for face, kind in faces:
            facing, lit = self._front_facing(face, interior)
            if not facing:
                continue
            if kind == "gable":
                fill = "temple_trim"
            else:
                fill = "temple_roof" if lit > 0 else "temple_roof_dark"
            primitives.append(
                Primitive("polygon", fill, "outline", points=tuple(project(*p) for p in face))
            )
            if kind == "slope":
                primitives.extend(self._roof_tiles(face, fill))
        primitives.append(
            Primitive("line", None, "temple_trim", points=(project(*ridge_a), project(*ridge_b)))
        )
        return primitives

    def _roof_tiles(self, face: list[XYZ], fill: str) -> list[Primitive]:
        eave_a, eave_b, ridge_b, ridge_a = face
        rows = int(math.dist(eave_a, ridge_a) // ROOF_TILE_SPACING_M)
        project = self.projection.world_to_native
        primitives = []
        for row in range(1, rows):
            t = row / rows
            start = tuple(e + (r - e) * t for e, r in zip(eave_a, ridge_a, strict=True))
            end = tuple(e + (r - e) * t for e, r in zip(eave_b, ridge_b, strict=True))
            primitives.append(
                Primitive("line", None, f"shade:{fill}", points=(project(*start), project(*end)))
            )
        return primitives

    def building(self, polygon: Polygon, properties: dict) -> list[Primitive]:
        height = properties["render_height_m"]
        temple = properties["is_temple"]
        shape = properties.get("roof_shape")
        if shape == "spire":
            return self.spire(polygon, height, temple)
        if shape == "prang":
            return self.prang(polygon, height)
        if shape == "chedi":
            return self.chedi(polygon, height)
        if shape == "gabled":
            primitives = self.gabled(polygon, height, temple)
            if primitives is not None:
                return primitives
        return self.prism(polygon, height, temple)

    def tree(self, point: Point, properties: dict) -> list[Primitive]:
        ppm = self.config.pixels_per_metre
        radius = properties["crown_radius_m"] * ppm
        base = self.projection.world_to_native(point.x, point.y)
        cx, cy = self.projection.world_to_native(
            point.x, point.y, self._tree_crown_centre(properties)
        )
        lx, ly = self.light_on_screen

        def disc(x: float, y: float, r: float) -> tuple[XY, ...]:
            steps = max(8, int(r * 2))
            return tuple(
                (
                    round(x + r * math.cos(2 * math.pi * k / steps)),
                    round(y + r * math.sin(2 * math.pi * k / steps)),
                )
                for k in range(steps)
            )

        return [
            Primitive("line", None, "tree_trunk", points=(base, (cx, cy))),
            Primitive("polygon", "tree_dark", "outline", points=disc(cx, cy, radius)),
            Primitive(
                "polygon",
                "tree",
                points=disc(cx + lx * radius * 0.2, cy + ly * radius * 0.2, radius * 0.75),
            ),
            Primitive(
                "polygon",
                "tree_light",
                points=disc(cx + lx * radius * 0.45, cy + ly * radius * 0.45, radius * 0.3),
            ),
        ]

    def buildings_and_vegetation(
        self,
        buildings: list[tuple[BaseGeometry, dict]],
        trees: list[tuple[BaseGeometry, dict]],
    ) -> tuple[Image.Image, Image.Image]:
        building_layer, vegetation_layer = self._blank(), self._blank()
        matrix = self.projection.screen_ground_matrix()
        lift_per_metre = self.cos_elevation * self.config.pixels_per_metre
        items: list[tuple[str, BaseGeometry, dict]] = []
        footprints: list[Polygon] = []
        keys: list[str] = []
        raised: list[float] = []
        for geometry, properties in buildings:
            for index, polygon in enumerate(_polygons(geometry)):
                polygon = orient(polygon)
                items.append(("building", polygon, properties))
                footprints.append(affine_transform(polygon, matrix))
                keys.append(f"{properties['source_id']}#{index}")
                raised.append(properties["render_height_m"] * lift_per_metre)
        for point, properties in trees:
            footprint = point.buffer(properties["crown_radius_m"] * TREE_FOOTPRINT_FRACTION)
            items.append(("tree", point, properties))
            footprints.append(affine_transform(footprint, matrix))
            keys.append(properties["source_id"])
            raised.append((properties["height_m"] + properties["crown_radius_m"]) * lift_per_metre)
        for index in back_to_front(footprints, keys, raised):
            kind, geometry, properties = items[index]
            if kind == "building":
                primitives = self.building(geometry, properties)
                self.paint(building_layer, primitives)
                self.paint(vegetation_layer, primitives, erase=True)
            else:
                self.paint(vegetation_layer, self.tree(geometry, properties))
        return building_layer, vegetation_layer


def render_layers(
    bounds: MapBounds, render: RenderConfig, layers: dict[str, list[tuple[BaseGeometry, dict]]]
) -> dict[str, Image.Image]:
    scene = SceneRenderer(bounds, render)
    buildings, vegetation = scene.buildings_and_vegetation(layers["buildings"], layers["trees"])
    return {
        "terrain": scene.terrain(),
        "water": scene.water(layers["water"]),
        "green": scene.green(layers["green"]),
        "roads": scene.roads(layers["roads"]),
        "shadows": scene.shadows(layers["buildings"], layers["trees"]),
        "buildings": buildings,
        "vegetation": vegetation,
    }


def composite(layers: dict[str, Image.Image], background: Color) -> Image.Image:
    size = layers[LAYER_ORDER[0]].size
    image = Image.new("RGBA", size, background)
    for name in LAYER_ORDER:
        image = Image.alpha_composite(image, layers[name])
    return image.convert("RGB")


def load_layers(
    processed_dir: Path, bounds: MapBounds
) -> dict[str, list[tuple[BaseGeometry, dict]]]:
    files = {
        "buildings": "buildings.enriched.geojson",
        "roads": "roads.geojson",
        "water": "water.geojson",
        "green": "green.geojson",
        "trees": "trees.enriched.geojson",
    }
    return {name: world_geometries(processed_dir / file, bounds) for name, file in files.items()}


def run(area: AreaConfig, render: RenderConfig, processed_dir: Path, build_dir: Path) -> Path:
    bounds = MapBounds.from_area(area)
    layers = render_layers(bounds, render, load_layers(processed_dir, bounds))
    layer_dir = build_dir / "layers"
    layer_dir.mkdir(parents=True, exist_ok=True)
    for index, name in enumerate(LAYER_ORDER):
        layers[name].save(layer_dir / f"{index}-{name}.png")
    image = composite(layers, parse_color(render.palette["background"]))
    output = build_dir / "render.png"
    image.save(output)
    log.info("rendered %dx%d native image to %s", image.width, image.height, output)
    return output
