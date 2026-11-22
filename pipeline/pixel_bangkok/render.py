"""Stage 4: deterministic procedural isometric render.

Input: processed GeoJSON layers (WGS84) for one area.
Output: build/<area>/render.png at native resolution plus one PNG per layer in
build/<area>/layers/. This image is the authoritative geometry reference.

Buildings and trees share one back-to-front order. Each is drawn into its own
layer; a building also clears the vegetation-layer pixels it covers, so trees
behind it stay hidden even though vegetation composites above buildings.
"""

from __future__ import annotations

import gc
import logging
import math
import random
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import shapely
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

LAYER_ORDER = (
    "terrain",
    "ground",
    "water",
    "green",
    "roads",
    "rail",
    "shadows",
    "buildings",
    "vegetation",
)
GROUND_ORDER = (
    "residential",
    "commercial",
    "institutional",
    "military",
    "religious",
    "palace",
    "parking",
    "paved",
)
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
# Prang proportions (fractions of footprint size and of total height), after the documented form
# of Wat Arun's prangs: four stepped terraces, a corncob tower of tiered ledges that rounds over
# at the top, and a thin metal finial (nabhasula) above it.
PRANG_TERRACES = ((1.0, 0.0, 0.06), (0.86, 0.06, 0.13), (0.72, 0.13, 0.2), (0.58, 0.2, 0.26))
PRANG_TOWER = (0.26, 0.84, 14)
PRANG_TOWER_RADIUS = 0.42
PRANG_LEDGE = 0.93
PRANG_FINIAL = (0.06, 0.012)
CHEDI_PLINTHS = ((1.0, 0.0, 0.1), (0.9, 0.1, 0.16))
CHEDI_BELL = (0.16, 0.5, 6)
CHEDI_HARMIKA = (0.3, 0.5, 0.56)
MATERIAL_TOWER_HEIGHT_M = 25.0
MATERIAL_LOWRISE_HEIGHT_M = 7.0
MATERIAL_LOWRISE_AREA_M2 = 400.0
CORRUGATION_SPACING_M = 0.7
TRADITIONAL_GROUNDS = {"religious", "palace"}
TREE_FOOTPRINT_FRACTION = 0.5
TRANSPARENT = (0, 0, 0, 0)
PARAPET_INSET_M = 0.3
PARAPET_HEIGHT_M = 0.4
DECK_CAP_SEGMENTS = 3
FRONT_CELL_PX = 32
TRAIN_CLEARANCE_PX = 16

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


def _snap(points: Any) -> list[tuple[int, int]]:
    """Floor to whole pixels so drawing is identical under whole-pixel shifts (blocks)."""
    return [(math.floor(x), math.floor(y)) for x, y in points]


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


@dataclass(frozen=True)
class Deck:
    """A short piece of an elevated road or rail way, sloping from z0 to z1."""

    line: LineString
    z0: float
    z1: float
    width: float
    kind: Literal["road", "rail"]
    start: float
    properties: dict
    key: str
    first: bool = False
    last: bool = False

    @property
    def footprint(self) -> Polygon:
        """Round joints between pieces so bends stay closed; square ends where the way ends."""
        radius = self.width / 2
        parts = [self.line.buffer(radius, cap_style="flat")]
        for end, flat in ((self.line.coords[0], self.first), (self.line.coords[-1], self.last)):
            if not flat:
                parts.append(Point(end).buffer(radius, quad_segs=DECK_CAP_SEGMENTS))
        merged = unary_union(parts)
        return merged if isinstance(merged, Polygon) else merged.convex_hull

    def z_at(self, x: float, y: float) -> float:
        length = self.line.length
        fraction = self.line.project(Point(x, y)) / length if length else 0.0
        return self.z0 + (self.z1 - self.z0) * fraction


def deck_height(properties: dict, distance: float, length: float, ramp_grade: float) -> float:
    """Deck top height `distance` metres along an elevated way, sloping down on ramp ends."""
    elevation = properties["elevation_m"]
    ramp = elevation / ramp_grade
    factor = 1.0
    if properties.get("ramp_start"):
        factor = min(factor, distance / ramp)
    if properties.get("ramp_end"):
        factor = min(factor, (length - distance) / ramp)
    return elevation * max(factor, 0.0)


def is_elevated(properties: dict) -> bool:
    return bool(properties.get("elevated")) or properties.get("level") == "elevated"


class SceneRenderer:
    def __init__(
        self, bounds: MapBounds, render: RenderConfig, projection: IsoProjection | None = None
    ) -> None:
        self.bounds = bounds
        self.config = render
        self.projection = projection or IsoProjection.create(bounds, render)
        self.size = (self.projection.native_width, self.projection.native_height)
        self.palette = {name: parse_color(value) for name, value in render.palette.items()}
        for material, colours in render.materials.items():
            for part, value in colours.items():
                if part != "roof_texture":
                    self.palette[f"{material}_{part}"] = parse_color(value)
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
        self.precincts: BaseGeometry = Polygon()

    def set_precincts(self, ground: list[tuple[BaseGeometry, dict]]) -> None:
        """Temple and palace grounds; buildings inside are drawn in traditional style."""
        self.precincts = unary_union([g for g, p in ground if p["category"] in TRADITIONAL_GROUNDS])
        shapely.prepare(self.precincts)

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

    def _mask(
        self, geometry: BaseGeometry, z: float = 0.0
    ) -> tuple[Image.Image, tuple[int, int]] | None:
        """Polygon mask cropped to its projected bounding box, with the box's top-left corner."""
        rings = []
        for polygon in _polygons(geometry):
            rings.append((self._ring(polygon.exterior.coords, z), 255))
            rings.extend((self._ring(interior.coords, z), 0) for interior in polygon.interiors)
        if not rings:
            return None
        xs = [x for ring, _ in rings for x, _ in ring]
        ys = [y for ring, _ in rings for _, y in ring]
        left = max(math.floor(min(xs)) - 1, 0)
        top = max(math.floor(min(ys)) - 1, 0)
        right = min(math.ceil(max(xs)) + 2, self.size[0])
        bottom = min(math.ceil(max(ys)) + 2, self.size[1])
        if right <= left or bottom <= top:
            return None
        mask = Image.new("L", (right - left, bottom - top), 0)
        draw = ImageDraw.Draw(mask)
        for ring, value in rings:
            draw.polygon([(x - left, y - top) for x, y in _snap(ring)], fill=value)
        return mask, (left, top)

    def _paste(self, layer: Image.Image, geometry: BaseGeometry, color: Color, z: float = 0.0):
        cropped = self._mask(geometry, z)
        if cropped is None:
            return
        mask, origin = cropped
        layer.paste(Image.new("RGBA", mask.size, color), origin, mask)

    def _fill(self, layer: Image.Image, geometry: BaseGeometry, color: Color) -> None:
        if geometry.is_empty:
            return
        self._paste(layer, geometry, color)

    def _outline(self, layer: Image.Image, geometry: BaseGeometry, color: Color) -> None:
        draw = ImageDraw.Draw(layer)
        for polygon in _polygons(geometry):
            for ring in (polygon.exterior, *polygon.interiors):
                draw.line(_snap(self._ring(ring.coords)), fill=color, width=1)

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
                    _snap(primitive.points),
                    fill=color(primitive.fill),
                    outline=None if erase else color(primitive.outline),
                )
            elif primitive.kind == "line":
                if not erase:
                    draw.line(_snap(primitive.points), fill=color(primitive.outline), width=1)
            elif primitive.geometry is not None and not primitive.geometry.is_empty:
                fill = color(primitive.fill)
                if fill is not None:
                    self._paste(layer, primitive.geometry, fill, primitive.z)
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
            draw.line(_snap(self._ring(line.coords)), fill=self.palette["foam"], width=1)
        return layer

    def ground(self, features: list[tuple[BaseGeometry, dict]]) -> Image.Image:
        layer = self._blank()
        for category in GROUND_ORDER:
            shapes = [g for g, p in features if p["category"] == category]
            if shapes:
                merged = self._clip(unary_union(shapes))
                self._fill(layer, merged, self.palette[f"ground_{category}"])
        return layer

    def green(self, features: list[tuple[BaseGeometry, dict]]) -> Image.Image:
        layer = self._blank()
        self._fill(layer, unary_union([g for g, _ in features]), self.palette["green"])
        return layer

    def roads(self, features: list[tuple[BaseGeometry, dict]]) -> Image.Image:
        layer = self._blank()
        groups: dict[str, list[BaseGeometry]] = {"pier": [], "path": [], "road": [], "major": []}
        centre_lines: list[LineString] = []
        sidewalks: list[BaseGeometry] = []
        style = self.config.roads
        for geometry, properties in features:
            if is_elevated(properties):
                continue
            category = properties["category"]
            is_line = geometry.geom_type in {"LineString", "MultiLineString"}
            if is_line:
                if (
                    category not in PATH_CATEGORIES
                    and category != "pier"
                    and properties["width_m"] >= style.marking_min_width_m
                ):
                    centre_lines.extend(_lines(geometry))
                if (
                    category not in PATH_CATEGORIES
                    and category != "pier"
                    and not properties.get("bridge")
                    and self.config.sidewalk_m > 0
                ):
                    sidewalks.append(
                        geometry.buffer(
                            properties["width_m"] / 2 + self.config.sidewalk_m, cap_style="flat"
                        )
                    )
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
        if sidewalks:
            self._fill(layer, self._clip(unary_union(sidewalks)), self.palette["sidewalk"])
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
                    draw.line(
                        _snap(self._ring(dash.coords)), fill=self.palette["road_marking"], width=1
                    )
                start += period
        return layer

    def _dashes(
        self, draw: ImageDraw.ImageDraw, line: LineString, dash: float, gap: float, fill: Color
    ) -> None:
        start = gap / 2
        while start < line.length:
            piece = substring(line, start, min(start + dash, line.length))
            if piece.length > 0:
                draw.line(_snap(self._ring(piece.coords)), fill=fill, width=1)
            start += dash + gap

    def rail(self, features: list[tuple[BaseGeometry, dict]]) -> Image.Image:
        """Rail at grade (ballast, sleepers, rails) and a dashed trace over underground lines."""
        layer = self._blank()
        transit = self.config.transit
        ground = [(g, p) for g, p in features if p.get("level") == "ground"]
        beds = []
        for geometry, properties in ground:
            span = (properties["tracks"] - 1) * transit.track_spacing_m + transit.ballast_width_m
            beds.append(geometry.buffer(span / 2, cap_style="flat"))
        if beds:
            self._fill(layer, self._clip(unary_union(beds)), self.palette["rail_bed"])
        draw = ImageDraw.Draw(layer)
        for geometry, properties in sorted(ground, key=lambda item: item[1]["source_id"]):
            tracks = properties["tracks"]
            span = (tracks - 1) * transit.track_spacing_m + transit.ballast_width_m
            for line in _lines(geometry):
                step = transit.sleeper_spacing_m
                distance = step / 2
                while distance < line.length:
                    a = line.interpolate(max(distance - 0.01, 0))
                    b = line.interpolate(min(distance + 0.01, line.length))
                    dx, dy = b.x - a.x, b.y - a.y
                    norm = math.hypot(dx, dy) or 1.0
                    nx, ny = -dy / norm * span * 0.4, dx / norm * span * 0.4
                    centre = line.interpolate(distance)
                    draw.line(
                        _snap(
                            self._ring(
                                [(centre.x - nx, centre.y - ny), (centre.x + nx, centre.y + ny)]
                            )
                        ),
                        fill=self.palette["rail_sleeper"],
                        width=1,
                    )
                    distance += step
                for offset in self._rail_offsets(tracks, transit.track_spacing_m):
                    for rail_line in _lines(line.offset_curve(offset)):
                        draw.line(
                            _snap(self._ring(rail_line.coords)),
                            fill=self.palette["rail_steel"],
                            width=1,
                        )
        for geometry, _ in sorted(
            (item for item in features if item[1].get("level") == "underground"),
            key=lambda item: item[1]["source_id"],
        ):
            for line in _lines(geometry):
                self._dashes(
                    draw,
                    line,
                    transit.subway_dash_m,
                    transit.subway_gap_m,
                    self.palette["subway_trace"],
                )
        return layer

    def _rail_offsets(self, tracks: int, spacing: float) -> list[float]:
        half = self.config.transit.rail_gauge_m / 2
        return [
            (index - (tracks - 1) / 2) * spacing + side
            for index in range(tracks)
            for side in (-half, half)
        ]

    def decks(
        self,
        roads: list[tuple[BaseGeometry, dict]],
        rail: list[tuple[BaseGeometry, dict]],
    ) -> list[Deck]:
        transit = self.config.transit
        pieces: list[Deck] = []
        for kind, features in (("road", roads), ("rail", rail)):
            for geometry, properties in features:
                if not is_elevated(properties):
                    continue
                width = (
                    properties["width_m"]
                    if kind == "road"
                    else properties["tracks"] * properties["track_width_m"]
                )
                prefix = f"{properties['source_id']}#{properties.get('part', 0)}"
                for line in _lines(geometry):
                    length = line.length
                    if length <= 0:
                        continue
                    count = max(1, math.ceil(length / transit.segment_m))
                    for index in range(count):
                        start, end = length * index / count, length * (index + 1) / count
                        if not self._piece_on_screen(line, start, end, width, properties):
                            continue
                        pieces.append(
                            Deck(
                                line=substring(line, start, end),
                                z0=self._deck_height(properties, start, length),
                                z1=self._deck_height(properties, end, length),
                                width=width,
                                kind=kind,
                                start=start,
                                properties=properties,
                                key=f"{prefix}:{index}",
                                first=index == 0,
                                last=index == count - 1,
                            )
                        )
        return pieces

    def _piece_on_screen(
        self, line: LineString, start: float, end: float, width: float, properties: dict
    ) -> bool:
        """Whether a deck piece, its pillars or its shadow can reach this image (or block)."""
        elevation = properties["elevation_m"]
        reach = width / 2 + elevation * self.config.shadow_length_per_metre + 2.0
        xs, ys = [], []
        for distance in (start, end):
            point = line.interpolate(distance)
            for z in (0.0, elevation):
                x, y = self.projection.world_to_native(point.x, point.y, z)
                xs.append(x)
                ys.append(y)
        margin = reach * self.config.pixels_per_metre * 2.5 + FRONT_CELL_PX
        return (
            max(xs) >= -margin
            and min(xs) <= self.size[0] + margin
            and max(ys) >= -margin
            and min(ys) <= self.size[1] + margin
        )

    def _deck_height(self, properties: dict, distance: float, length: float) -> float:
        return deck_height(properties, distance, length, self.config.transit.ramp_grade)

    def _pillar(self, centre: Point, direction: XY, top: float) -> list[Primitive]:
        half = self.config.transit.pillar_size_m / 2
        ux, uy = direction
        nx, ny = -uy, ux
        corners = [
            (centre.x + sx * ux * half + sy * nx * half, centre.y + sx * uy * half + sy * ny * half)
            for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))
        ]
        pillar = orient(Polygon(corners))
        project = self.projection.world_to_native
        primitives = []
        for a, b in self._edges(pillar):
            if not self._faces_camera(a, b):
                continue
            fill = self._wall_color(a, b, "viaduct")
            quad = (project(*a), project(*b), project(*b, top), project(*a, top))
            primitives.append(Primitive("polygon", fill, f"shade:{fill}", points=quad))
        return primitives

    def deck(self, deck: Deck) -> list[Primitive]:
        transit = self.config.transit
        project = self.projection.world_to_native
        line = deck.line
        primitives: list[Primitive] = []
        spacing = transit.pillar_spacing_m
        distance = math.ceil((deck.start - spacing / 2) / spacing) * spacing + spacing / 2
        while distance < deck.start + line.length:
            local = distance - deck.start
            centre = line.interpolate(local)
            ahead = line.interpolate(min(local + 0.5, line.length))
            behind = line.interpolate(max(local - 0.5, 0))
            dx, dy = ahead.x - behind.x, ahead.y - behind.y
            norm = math.hypot(dx, dy) or 1.0
            top = deck.z_at(centre.x, centre.y) - transit.deck_thickness_m
            if top > transit.deck_thickness_m:
                primitives += self._pillar(centre, (dx / norm, dy / norm), top)
            distance += spacing
        footprint = orient(deck.footprint)
        coords = list(footprint.exterior.coords)
        thickness = transit.deck_thickness_m
        for a, b in self._edges(footprint):
            if not self._faces_camera(a, b):
                continue
            za, zb = deck.z_at(*a), deck.z_at(*b)
            bottom_a, bottom_b = max(za - thickness, 0.0), max(zb - thickness, 0.0)
            fill = self._wall_color(a, b, "viaduct")
            primitives.append(
                Primitive(
                    "polygon",
                    fill,
                    points=(
                        project(*a, bottom_a),
                        project(*b, bottom_b),
                        project(*b, zb),
                        project(*a, za),
                    ),
                )
            )
            primitives.append(
                Primitive(
                    "line",
                    None,
                    "shade:viaduct_wall_dark",
                    points=(project(*a, bottom_a), project(*b, bottom_b)),
                )
            )
        surface = "road_major" if deck.kind == "road" else "viaduct_roof"
        primitives.append(
            Primitive(
                "polygon",
                surface,
                points=tuple(project(x, y, deck.z_at(x, y)) for x, y in coords),
            )
        )

        def lifted(path: LineString, lift: float) -> tuple[XY, ...]:
            return tuple(project(x, y, deck.z_at(x, y) + lift) for x, y in path.coords)

        if deck.kind == "rail":
            for offset in self._rail_offsets(
                deck.properties["tracks"], deck.properties["track_width_m"]
            ):
                for rail_line in _lines(line.offset_curve(offset)):
                    primitives.append(
                        Primitive("line", None, "rail_steel", points=lifted(rail_line, 0.1))
                    )
        elif deck.width >= self.config.roads.marking_min_width_m:
            style = self.config.roads
            period = style.dash_m + style.gap_m
            start = math.ceil((deck.start - style.gap_m / 2) / period) * period + style.gap_m / 2
            while start < deck.start + line.length:
                a = max(start - deck.start, 0.0)
                b = min(start - deck.start + style.dash_m, line.length)
                if b > a:
                    primitives.append(
                        Primitive(
                            "line", None, "road_marking", points=lifted(substring(line, a, b), 0.0)
                        )
                    )
                start += period
        for side in (1, -1):
            for edge in _lines(line.offset_curve(side * (deck.width / 2 - PARAPET_INSET_M))):
                primitives.append(
                    Primitive(
                        "line", None, "viaduct_parapet", points=lifted(edge, PARAPET_HEIGHT_M)
                    )
                )
        return primitives

    def _tree_crown_centre(self, properties: dict) -> float:
        radius = properties["crown_radius_m"]
        return max(properties["height_m"] - radius, radius)

    def shadows(
        self,
        buildings: list[tuple[BaseGeometry, dict]],
        trees: list[tuple[BaseGeometry, dict]],
        decks: list[Deck] = (),  # type: ignore[assignment]
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
        for deck in decks:
            length = (deck.z0 + deck.z1) / 2 * per_metre
            swept.append(translate(deck.footprint, away[0] * length, away[1] * length))
        layer = self._blank()
        self._fill(layer, self._clip(unary_union(swept)), self.palette["shadow"])
        contact = self._blank()
        footprints = [geometry.buffer(CONTACT_SHADOW_M) for geometry, _ in buildings]
        self._fill(contact, self._clip(unary_union(footprints)), self.palette["contact_shadow"])
        return Image.alpha_composite(layer, contact)

    def _wall_color(self, a: XY, b: XY, skin: str) -> str:
        nx, ny = b[1] - a[1], a[0] - b[0]
        length = math.hypot(nx, ny) or 1.0
        lit = (nx * self.toward_light[0] + ny * self.toward_light[1]) / length
        tone = "light" if lit > WALL_LIGHT_THRESHOLD else "dark"
        return f"{skin}_wall_{tone}"

    def _skin(self, polygon: Polygon, properties: dict, traditional: bool) -> str:
        if properties.get("facade") == "plain":
            return "monument"
        return "temple" if traditional else self.material(polygon, properties)

    def material(self, polygon: Polygon, properties: dict) -> str:
        """Deterministic stylised material for a non-temple building (not a source fact)."""
        groups = self.config.material_groups
        height = properties["render_height_m"]
        if height >= MATERIAL_TOWER_HEIGHT_M:
            pool = groups["tower"]
        elif height <= MATERIAL_LOWRISE_HEIGHT_M and polygon.area <= MATERIAL_LOWRISE_AREA_M2:
            pool = groups["lowrise"]
        else:
            pool = groups["general"]
        key = zlib.crc32(properties["source_id"].encode()) ^ self.config.seed
        return pool[key % len(pool)]

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

    def _windows(self, a: XY, b: XY, wall_height: float, skin: str) -> list[Primitive]:
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
        fill = f"{skin}_window" if f"{skin}_window" in self.palette else "window"
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

    def _walls(
        self, polygon: Polygon, wall_height: float, skin: str, base: float = 0.0
    ) -> list[Primitive]:
        project = self.projection.world_to_native
        primitives = []
        for a, b in self._edges(polygon):
            if not self._faces_camera(a, b):
                continue
            quad = (
                project(*a, base),
                project(*b, base),
                project(*b, wall_height),
                project(*a, wall_height),
            )
            fill = self._wall_color(a, b, skin)
            primitives.append(Primitive("polygon", fill, f"shade:{fill}", points=quad))
            if base == 0 and skin != "monument":
                primitives.extend(self._windows(a, b, wall_height, skin))
        return primitives

    def _roof_outline(self, polygon: Polygon, height: float) -> list[Primitive]:
        return [
            Primitive("line", None, "outline", points=tuple(self._ring(ring.coords, height)))
            for ring in (polygon.exterior, *polygon.interiors)
        ]

    def prism(
        self, polygon: Polygon, height: float, skin: str, source_id: str = "", base: float = 0.0
    ) -> list[Primitive]:
        primitives = self._walls(polygon, height, skin, base)
        if skin == "temple":
            primitives.append(Primitive("area", "temple_roof", geometry=polygon, z=height))
            return primitives + self._roof_outline(polygon, height)
        primitives.append(Primitive("area", f"{skin}_roof_edge", geometry=polygon, z=height))
        inner = polygon.buffer(-self.config.facade.parapet_m, join_style="mitre")
        if not inner.is_empty:
            primitives.append(Primitive("area", f"{skin}_roof", geometry=inner, z=height))
            if self.config.materials.get(skin, {}).get("roof_texture") == "metal":
                primitives += self._corrugation(polygon, inner, height, f"shade:{skin}_roof")
            elif skin != "monument":
                primitives += self._rooftop_items(inner, height, source_id)
        return primitives + self._roof_outline(polygon, height)

    def _corrugation(
        self, footprint: Polygon, roof: BaseGeometry, height: float, color: str
    ) -> list[Primitive]:
        rectangle = footprint.minimum_rotated_rectangle
        if not isinstance(rectangle, Polygon):
            return []
        corners = list(rectangle.exterior.coords)[:4]
        long_side = max(range(4), key=lambda i: math.dist(corners[i], corners[(i + 1) % 4]))
        a, b = corners[long_side], corners[(long_side + 1) % 4]
        length = math.dist(a, b) or 1.0
        ux, uy = (b[0] - a[0]) / length, (b[1] - a[1]) / length
        nx, ny = -uy, ux
        centre = footprint.centroid
        reach = max(math.dist(c, (centre.x, centre.y)) for c in corners)
        primitives = []
        steps = int(2 * reach / CORRUGATION_SPACING_M)
        for step in range(steps + 1):
            offset = -reach + step * CORRUGATION_SPACING_M
            ox, oy = centre.x + nx * offset, centre.y + ny * offset
            line = LineString(
                [(ox - ux * reach, oy - uy * reach), (ox + ux * reach, oy + uy * reach)]
            ).intersection(roof)
            for part in _lines(line):
                primitives.append(
                    Primitive("line", None, color, points=tuple(self._ring(part.coords, height)))
                )
        return primitives

    def _rooftop_items(self, roof: BaseGeometry, height: float, source_id: str) -> list[Primitive]:
        """Decorative water tanks and air-conditioning units; not source data."""
        settings = self.config.rooftop
        if height < settings.min_height_m or roof.area < settings.min_area_m2:
            return []
        rng = random.Random(zlib.crc32(source_id.encode()) ^ self.config.seed)
        minx, miny, maxx, maxy = roof.bounds
        items: list[tuple[Polygon, float, str]] = []
        attempts = 0
        while len(items) < settings.max_items and attempts < 20:
            attempts += 1
            tank = not items and rng.random() < 0.8
            size = settings.tank_size_m if tank else settings.unit_size_m
            x = rng.uniform(minx, maxx - size)
            y = rng.uniform(miny, maxy - size)
            footprint = box(x, y, x + size, y + size)
            if not roof.contains(footprint) or any(footprint.intersects(i) for i, _, _ in items):
                continue
            items.append((footprint, size if tank else size * 0.7, "tank" if tank else "unit"))
        items.sort(key=lambda item: -self.projection.depth(item[0].centroid.x, item[0].centroid.y))
        primitives = []
        for footprint, item_height, kind in items:
            primitives += self.frustum(
                orient(footprint),
                height,
                orient(footprint),
                height + item_height,
                f"rooftop_{kind}_roof",
                skin=f"rooftop_{kind}",
            )
        return primitives

    def spire(self, polygon: Polygon, height: float, skin: str) -> list[Primitive]:
        project = self.projection.world_to_native
        centroid = polygon.centroid
        apex = project(centroid.x, centroid.y, height)
        primitives = []
        for a, b in self._edges(Polygon(polygon.exterior)):
            fill = self._wall_color(a, b, skin)
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
        skin: str = "temple",
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
            fill = self._wall_color(a, b, skin)
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
        """Khmer-style prang: stepped terraces, a corncob tower of tiered ledges, a thin finial."""
        primitives = []
        for factor, bottom, top in PRANG_TERRACES:
            tier = self._scaled(polygon, factor)
            primitives += self.frustum(
                tier, bottom * height, tier, top * height, "temple_wall_light", "temple_trim"
            )
        start, end, segments = PRANG_TOWER

        def radius(t: float) -> float:
            # Nearly upright at the base, rounding over towards the top like a corncob.
            return PRANG_TOWER_RADIUS * max(1 - t**2.4, 0.0) ** 0.55 + PRANG_FINIAL[0]

        for index in range(segments):
            t0, t1 = index / segments, (index + 1) / segments
            primitives += self.frustum(
                self._scaled(polygon, radius(t0)),
                (start + (end - start) * t0) * height,
                self._scaled(polygon, radius(t1) * PRANG_LEDGE),
                (start + (end - start) * t1) * height,
                "temple_wall_light",
                "temple_trim" if index % 2 else None,
            )
        base, tip = PRANG_FINIAL
        primitives += self.frustum(
            self._scaled(polygon, base),
            end * height,
            self._scaled(polygon, tip),
            height,
            None,
            "temple_trim",
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

    def gabled(self, polygon: Polygon, height: float, skin: str) -> list[Primitive] | None:
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
        primitives = self._walls(polygon, eave, skin)
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
        traditional = properties["is_temple"] or (
            not self.precincts.is_empty and self.precincts.contains(polygon.representative_point())
        )
        skin = self._skin(polygon, properties, traditional)
        shape = properties.get("roof_shape")
        if traditional and shape == "flat":
            shape = "gabled"
        if shape == "spire":
            return self.spire(polygon, height, skin)
        if shape == "prang":
            return self.prang(polygon, height)
        if shape == "chedi":
            return self.chedi(polygon, height)
        if shape == "gabled":
            primitives = self.gabled(polygon, height, skin)
            if primitives is not None:
                return primitives
        return self.prism(polygon, height, skin, properties["source_id"])

    def building_parts(
        self, geometry: BaseGeometry, parts: list[tuple[Polygon, dict]], properties: dict
    ) -> list[Primitive]:
        """A building drawn from its OSM building:part pieces, each from min_height to height.

        Lower pieces first; at the same level a piece that encloses others (a plinth) before
        them; the rest back to front.
        """
        outline = max(_polygons(geometry), key=lambda polygon: polygon.area)
        traditional = properties["is_temple"] or (
            not self.precincts.is_empty and self.precincts.contains(outline.representative_point())
        )
        skin = self._skin(outline, properties, traditional)

        def encloses(piece: Polygon) -> bool:
            grown = piece.buffer(0.05)
            return any(other is not piece and grown.contains(other) for other, _ in parts)

        ordered = sorted(
            parts,
            key=lambda part: (
                part[1]["min_height_m"],
                0 if encloses(part[0]) else 1,
                -self.projection.depth(part[0].centroid.x, part[0].centroid.y),
            ),
        )
        primitives: list[Primitive] = []
        for piece, part in ordered:
            for polygon in _polygons(piece):
                primitives += self.prism(
                    orient(polygon),
                    part["height_m"],
                    skin,
                    part["source_id"],
                    base=part["min_height_m"],
                )
        return primitives

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

    def _cells(self, primitives: list[Primitive], lift_px: int = 0) -> set[tuple[int, int]]:
        xs: list[float] = []
        ys: list[float] = []
        for primitive in primitives:
            if primitive.points:
                xs.extend(x for x, _ in primitive.points)
                ys.extend(y for _, y in primitive.points)
        if not xs:
            return set()
        size = FRONT_CELL_PX
        return {
            (cx, cy)
            for cx in range(math.floor(min(xs)) // size, math.floor(max(xs)) // size + 1)
            for cy in range(
                (math.floor(min(ys)) - lift_px) // size, math.floor(max(ys)) // size + 1
            )
        }

    def buildings_and_vegetation(
        self,
        buildings: list[tuple[BaseGeometry, dict]],
        trees: list[tuple[BaseGeometry, dict]],
        decks: list[Deck] = (),  # type: ignore[assignment]
        parts: dict[str, list[tuple[Polygon, dict]]] | None = None,
    ) -> tuple[Image.Image, Image.Image, Image.Image]:
        """Buildings, vegetation and `front`: what stands in front of an elevated deck.

        `parts`: building:part pieces by building source_id (see `parts_by_building`).
        """
        parts = parts or {}
        building_layer, vegetation_layer, front = self._blank(), self._blank(), self._blank()
        matrix = self.projection.screen_ground_matrix()
        lift_per_metre = self.cos_elevation * self.config.pixels_per_metre
        items: list[tuple[str, Any, dict]] = []
        footprints: list[Polygon] = []
        keys: list[str] = []
        raised: list[float] = []
        for geometry, properties in buildings:
            pieces = parts.get(properties["source_id"])
            if pieces:
                items.append(("parts", (geometry, pieces), properties))
                footprints.append(affine_transform(geometry, matrix))
                keys.append(properties["source_id"])
                raised.append(max(part["height_m"] for _, part in pieces) * lift_per_metre)
                continue
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
        for deck in decks:
            items.append(("deck", deck, deck.properties))
            footprints.append(affine_transform(deck.footprint, matrix))
            keys.append(deck.key)
            raised.append(max(deck.z0, deck.z1) * lift_per_metre)
        deck_cells: set[tuple[int, int]] = set()
        soft = [kind == "tree" for kind, _, _ in items]
        for index in back_to_front(footprints, keys, raised, soft):
            kind, geometry, properties = items[index]
            if kind == "deck":
                primitives = self.deck(geometry)
                self.paint(building_layer, primitives)
                self.paint(vegetation_layer, primitives, erase=True)
                self.paint(front, primitives, erase=True)
                deck_cells |= self._cells(primitives, TRAIN_CLEARANCE_PX)
                continue
            if kind in {"building", "parts"}:
                primitives = (
                    self.building(geometry, properties)
                    if kind == "building"
                    else self.building_parts(*geometry, properties)
                )
                self.paint(building_layer, primitives)
                self.paint(vegetation_layer, primitives, erase=True)
            else:
                primitives = self.tree(geometry, properties)
                self.paint(vegetation_layer, primitives)
            if deck_cells and not deck_cells.isdisjoint(self._cells(primitives)):
                self.paint(front, primitives)
        return building_layer, vegetation_layer, front


def render_layers(
    bounds: MapBounds,
    render: RenderConfig,
    layers: dict[str, list[tuple[BaseGeometry, dict]]],
    projection: IsoProjection | None = None,
) -> dict[str, Image.Image]:
    scene = SceneRenderer(bounds, render, projection)
    scene.set_precincts(layers.get("ground", []))
    rail = layers.get("rail", [])
    decks = scene.decks(layers["roads"], rail)
    parts = parts_by_building(layers["buildings"], layers.get("building_parts", []))
    buildings, vegetation, front = scene.buildings_and_vegetation(
        layers["buildings"], layers["trees"], decks, parts
    )
    # A building drawn from parts casts each part's shadow, not its outline's.
    shadow_buildings = [
        item for item in layers["buildings"] if item[1]["source_id"] not in parts
    ] + [
        (piece, part | {"render_height_m": part["height_m"]})
        for pieces in parts.values()
        for piece, part in pieces
    ]
    return {
        "terrain": scene.terrain(),
        "ground": scene.ground(layers.get("ground", [])),
        "water": scene.water(layers["water"]),
        "green": scene.green(layers["green"]),
        "roads": scene.roads(layers["roads"]),
        "rail": scene.rail(rail),
        "shadows": scene.shadows(shadow_buildings, layers["trees"], decks),
        "buildings": buildings,
        "vegetation": vegetation,
        "front": front,
    }


def parts_by_building(
    buildings: list[tuple[BaseGeometry, dict]], parts: list[tuple[BaseGeometry, dict]]
) -> dict[str, list[tuple[Polygon, dict]]]:
    """building:part pieces grouped under the building that contains them.

    As in OSM's Simple 3D Buildings, a building with parts is drawn from its parts alone.
    A building is listed only when every part inside it has a sourced height and min_height;
    otherwise its outline is drawn as before, so no volume is dropped or guessed.
    """
    pieces = [(orient(polygon), properties) for g, properties in parts for polygon in _polygons(g)]
    if not pieces:
        return {}
    tree = shapely.STRtree([polygon for polygon, _ in pieces])
    grouped: dict[str, list[tuple[Polygon, dict]]] = {}
    for geometry, properties in buildings:
        inside = sorted(
            (
                pieces[index]
                for index in tree.query(geometry)
                if geometry.contains(pieces[index][0].representative_point())
            ),
            key=lambda piece: piece[1]["source_id"],
        )
        if inside and all(
            part["height_m"] is not None and part["min_height_m"] is not None for _, part in inside
        ):
            grouped[properties["source_id"]] = inside
    return grouped


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
        "building_parts": "building_parts.geojson",
        "roads": "roads.geojson",
        "rail": "rail.geojson",
        "water": "water.geojson",
        "green": "green.geojson",
        "ground": "ground.geojson",
        "trees": "trees.enriched.geojson",
    }
    from .trees import COMPACT_NAME, read_compact

    compact = processed_dir / COMPACT_NAME
    return {
        name: read_compact(compact)
        if name == "trees" and compact.exists()
        else world_geometries(processed_dir / file, bounds)
        for name, file in files.items()
        if name not in {"ground", "rail", "building_parts"} or (processed_dir / file).exists()
    }


def inputs_key(render: RenderConfig, bounds: MapBounds, processed_dir: Path) -> str:
    """Identifies a render's inputs (config, bounds, processed layer files) for resuming."""
    import dataclasses
    import hashlib
    import json

    digest = hashlib.sha256(json.dumps(dataclasses.asdict(render), sort_keys=True).encode())
    digest.update(json.dumps(bounds.to_dict(), sort_keys=True).encode())
    for path in sorted(processed_dir.glob("*.geojson")):
        stat = path.stat()
        digest.update(f"{path.name}:{stat.st_size}:{stat.st_mtime_ns}".encode())
    return digest.hexdigest()


def run(area: AreaConfig, render: RenderConfig, processed_dir: Path, build_dir: Path) -> Path:
    from .blocks import render_blocks

    bounds = MapBounds.from_area(area)
    blocks_dir = build_dir / "blocks"
    layers = load_layers(processed_dir, bounds)
    gc.collect()
    gc.freeze()
    info = render_blocks(
        bounds,
        render,
        layers,
        blocks_dir,
        inputs_key=inputs_key(render, bounds, processed_dir),
    )
    log.info(
        "rendered %dx%d native image in %d blocks to %s",
        info["width"],
        info["height"],
        len(info["blocks"]),
        blocks_dir,
    )
    return blocks_dir
