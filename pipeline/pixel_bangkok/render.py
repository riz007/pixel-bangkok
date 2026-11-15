"""Stage 4: deterministic procedural isometric render.

Input: processed GeoJSON layers (WGS84) for one area.
Output: build/<area>/render.png at native resolution plus one PNG per layer in
build/<area>/layers/. This image is the authoritative geometry reference.
"""

from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw
from shapely.affinity import translate
from shapely.geometry import MultiPolygon, Polygon, box
from shapely.geometry.base import BaseGeometry
from shapely.geometry.polygon import orient
from shapely.ops import unary_union

from .config import AreaConfig, RenderConfig
from .crs import MapBounds
from .geojson_io import world_geometries
from .projection import IsoProjection

log = logging.getLogger(__name__)

LAYER_ORDER = ("terrain", "water", "green", "roads", "shadows", "buildings", "vegetation")
PATH_CATEGORIES = {"footway", "path", "steps", "pedestrian", "cycleway"}
MAJOR_CATEGORIES = {"motorway", "trunk", "primary", "secondary", "tertiary"}
WALL_LIGHT_THRESHOLD = 0.1

Color = tuple[int, int, int, int]


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


class SceneRenderer:
    def __init__(self, bounds: MapBounds, render: RenderConfig) -> None:
        self.bounds = bounds
        self.config = render
        self.projection = IsoProjection.create(bounds, render)
        self.size = (self.projection.native_width, self.projection.native_height)
        self.palette = {name: parse_color(value) for name, value in render.palette.items()}
        camera = math.radians(render.camera_azimuth_deg)
        self.toward_camera = (-math.sin(camera), -math.cos(camera))
        light = math.radians(render.light_azimuth_deg)
        self.toward_light = (math.sin(light), math.cos(light))

    def _blank(self) -> Image.Image:
        return Image.new("RGBA", self.size, (0, 0, 0, 0))

    def _ring(self, coords: Any, z: float = 0.0) -> list[tuple[float, float]]:
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
        return layer

    def green(self, features: list[tuple[BaseGeometry, dict]]) -> Image.Image:
        layer = self._blank()
        self._fill(layer, unary_union([g for g, _ in features]), self.palette["green"])
        return layer

    def _clip(self, geometry: BaseGeometry) -> BaseGeometry:
        return geometry.intersection(box(0, 0, self.bounds.width_m, self.bounds.height_m))

    def roads(self, features: list[tuple[BaseGeometry, dict]]) -> Image.Image:
        layer = self._blank()
        groups: dict[str, list[BaseGeometry]] = {"pier": [], "path": [], "road": [], "major": []}
        for geometry, properties in features:
            category = properties["category"]
            if geometry.geom_type in {"LineString", "MultiLineString"}:
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
        for group in ("pier", "path", "road", "major"):
            merged = self._clip(unary_union(groups[group]))
            self._fill(layer, merged, self.palette[colors[group]])
        return layer

    def shadows(self, buildings: list[tuple[BaseGeometry, dict]]) -> Image.Image:
        layer = self._blank()
        swept: list[BaseGeometry] = []
        for geometry, properties in buildings:
            length = properties["render_height_m"] * self.config.shadow_length_per_metre
            dx, dy = -self.toward_light[0] * length, -self.toward_light[1] * length
            for polygon in _polygons(geometry):
                coords = list(polygon.exterior.coords)
                quads = [
                    Polygon([a, b, (b[0] + dx, b[1] + dy), (a[0] + dx, a[1] + dy)])
                    for a, b in zip(coords, coords[1:], strict=False)
                ]
                swept.append(
                    unary_union([q.buffer(0) for q in quads] + [translate(polygon, dx, dy)])
                )
        self._fill(layer, self._clip(unary_union(swept)), self.palette["shadow"])
        return layer

    def _wall_color(self, a: tuple[float, float], b: tuple[float, float], temple: bool) -> Color:
        nx, ny = b[1] - a[1], a[0] - b[0]
        length = math.hypot(nx, ny) or 1.0
        lit = (nx * self.toward_light[0] + ny * self.toward_light[1]) / length
        tone = "light" if lit > WALL_LIGHT_THRESHOLD else "dark"
        return self.palette[f"{'temple' if temple else 'building'}_wall_{tone}"]

    def _edges(self, polygon: Polygon) -> list[tuple[tuple[float, float], tuple[float, float]]]:
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

    def _faces_camera(self, a: tuple[float, float], b: tuple[float, float]) -> bool:
        nx, ny = b[1] - a[1], a[0] - b[0]
        return nx * self.toward_camera[0] + ny * self.toward_camera[1] > 0

    def _draw_prism(self, layer: Image.Image, polygon: Polygon, height: float, temple: bool):
        draw = ImageDraw.Draw(layer)
        outline = self.palette["outline"]
        project = self.projection.world_to_native
        for a, b in self._edges(polygon):
            if not self._faces_camera(a, b):
                continue
            quad = [project(*a), project(*b), project(*b, height), project(*a, height)]
            draw.polygon(quad, fill=self._wall_color(a, b, temple), outline=outline)
        roof = self.palette["temple_roof" if temple else "building_roof"]
        if polygon.interiors:
            layer.paste(Image.new("RGBA", self.size, roof), (0, 0), self._mask(polygon, height))
            draw = ImageDraw.Draw(layer)
        else:
            draw.polygon(self._ring(polygon.exterior.coords, height), fill=roof)
        for ring in (polygon.exterior, *polygon.interiors):
            draw.line(self._ring(ring.coords, height), fill=outline, width=1)

    def _draw_spire(self, layer: Image.Image, polygon: Polygon, height: float, temple: bool):
        draw = ImageDraw.Draw(layer)
        project = self.projection.world_to_native
        centroid = polygon.centroid
        apex = project(centroid.x, centroid.y, height)
        for a, b in self._edges(Polygon(polygon.exterior)):
            draw.polygon(
                [project(*a), project(*b), apex],
                fill=self._wall_color(a, b, temple),
                outline=self.palette["outline"],
            )

    def buildings(self, features: list[tuple[BaseGeometry, dict]]) -> Image.Image:
        layer = self._blank()
        parts = [
            (orient(polygon), properties)
            for geometry, properties in features
            for polygon in _polygons(geometry)
        ]
        parts.sort(
            key=lambda part: (
                -self.projection.depth(part[0].centroid.x, part[0].centroid.y),
                part[1]["source_id"],
            )
        )
        for polygon, properties in parts:
            height = properties["render_height_m"]
            if properties.get("roof_shape") == "spire":
                self._draw_spire(layer, polygon, height, properties["is_temple"])
            else:
                self._draw_prism(layer, polygon, height, properties["is_temple"])
        return layer

    def vegetation(self, trees: list[tuple[BaseGeometry, dict]]) -> Image.Image:
        layer = self._blank()
        draw = ImageDraw.Draw(layer)
        ppm = self.config.pixels_per_metre
        radius = self.config.tree_canopy_radius_m * ppm
        ordered = sorted(trees, key=lambda item: -self.projection.depth(item[0].x, item[0].y))
        for point, _ in ordered:
            base = self.projection.world_to_native(point.x, point.y)
            top = self.projection.world_to_native(point.x, point.y, self.config.tree_height_m)
            draw.line([base, top], fill=self.palette["tree_trunk"], width=1)
            draw.ellipse(
                [top[0] - radius, top[1] - radius, top[0] + radius, top[1] + radius],
                fill=self.palette["tree"],
                outline=self.palette["outline"],
            )
            draw.ellipse(
                [top[0] - radius / 2, top[1] - radius / 2, top[0], top[1]],
                fill=self.palette["tree_light"],
            )
        return layer


def render_layers(
    bounds: MapBounds, render: RenderConfig, layers: dict[str, list[tuple[BaseGeometry, dict]]]
) -> dict[str, Image.Image]:
    scene = SceneRenderer(bounds, render)
    return {
        "terrain": scene.terrain(),
        "water": scene.water(layers["water"]),
        "green": scene.green(layers["green"]),
        "roads": scene.roads(layers["roads"]),
        "shadows": scene.shadows(layers["buildings"]),
        "buildings": scene.buildings(layers["buildings"]),
        "vegetation": scene.vegetation(layers["trees"]),
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
        "trees": "trees.geojson",
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
