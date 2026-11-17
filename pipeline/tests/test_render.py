import io

import pytest
from shapely.geometry import Point, box, shape

from pixel_bangkok.heights import derive_height, roof_shape
from pixel_bangkok.normalise import normalise
from pixel_bangkok.pixelart import apply_pixel_art, unique_colors
from pixel_bangkok.projection import IsoProjection
from pixel_bangkok.render import SceneRenderer, composite, parse_color, render_layers


@pytest.fixture
def scene(raw_osm, area, bounds, render_config):
    layers, _ = normalise(raw_osm, area, render_config)
    world = {}
    for name, features in layers.items():
        world[name] = []
        for item in features:
            properties = dict(item["properties"])
            if name == "buildings":
                derived = derive_height(
                    properties["source_height"],
                    properties["source_levels"],
                    render_config.heights,
                )
                properties["render_height_m"] = derived.render_height_m
                properties["roof_shape"] = roof_shape(properties, None)
            if name == "trees":
                properties["height_m"] = 6.0
                properties["crown_radius_m"] = 2.5
            geometry = bounds.geometry_to_world(shape(item["geometry"]))
            world[name].append((geometry, properties))
    return world


def _render(bounds, render_config, scene):
    layers = render_layers(bounds, render_config, scene)
    return composite(layers, parse_color(render_config.palette["background"]))


def _png(image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_render_is_deterministic(bounds, render_config, scene):
    assert _png(_render(bounds, render_config, scene)) == _png(
        _render(bounds, render_config, scene)
    )


def test_image_size_matches_projection(bounds, render_config, scene):
    projection = IsoProjection.create(bounds, render_config)
    image = _render(bounds, render_config, scene)
    assert image.size == (projection.native_width, projection.native_height)


def test_features_land_where_the_projection_says(bounds, render_config, scene):
    projection = IsoProjection.create(bounds, render_config)
    image = _render(bounds, render_config, scene)
    palette = {name: parse_color(value)[:3] for name, value in render_config.palette.items()}

    def pixel(x, y, z=0.0):
        px, py = projection.world_to_native(x, y, z)
        return image.getpixel((round(px), round(py)))

    assert pixel(50, 50, 12) == palette["building_roof"]
    assert pixel(95, 45, 6) in {
        palette["temple_roof"],
        palette["temple_roof_dark"],
        palette["temple_trim"],
    }
    assert pixel(15, 85) == palette["water"]
    assert pixel(100, 11.5) == palette["road"]
    assert pixel(165, 45) == palette["green"]
    assert pixel(100, 60) == palette["terrain"]
    assert image.getpixel((0, 0)) == palette["background"]


def test_pixel_art_keeps_geometry_and_limited_palette(bounds, render_config, scene):
    image = _render(bounds, render_config, scene)
    master = apply_pixel_art(image, render_config)
    scale = render_config.upscale
    assert master.size == (image.width * scale, image.height * scale)
    assert unique_colors(master) <= 2 * len(render_config.palette)
    projection = IsoProjection.create(bounds, render_config)
    px, py = projection.world_to_master(50, 50, 12)
    roof = parse_color(render_config.palette["building_roof"])[:3]
    assert master.getpixel((round(px), round(py))) == roof
    assert _png(apply_pixel_art(image, render_config)) == _png(master)


def _building(height=12.0, roof="flat", temple=False, footprint=None):
    return (
        footprint if footprint is not None else box(40, 40, 60, 60),
        {
            "source_id": "way/1",
            "render_height_m": height,
            "is_temple": temple,
            "roof_shape": roof,
        },
    )


def _tree(x, y, source_id):
    return Point(x, y), {"source_id": source_id, "height_m": 6.0, "crown_radius_m": 2.5}


def test_trees_are_hidden_behind_buildings_and_shown_in_front(bounds, render_config):
    scene = SceneRenderer(bounds, render_config)
    behind = _tree(38, 62, "behind")
    in_front = _tree(62, 38, "front")
    assert scene.projection.depth(38, 62) > scene.projection.depth(50, 50)
    buildings, vegetation = scene.buildings_and_vegetation([_building()], [behind, in_front])

    def crown_pixel(tree):
        point, properties = tree
        x, y = scene.projection.world_to_native(point.x, point.y, 3.5)
        return round(x), round(y)

    hidden = crown_pixel(behind)
    assert buildings.getpixel(hidden)[3] == 255
    assert vegetation.getpixel(hidden)[3] == 0
    assert vegetation.getpixel(crown_pixel(in_front))[3] == 255


def test_windows_follow_floors_and_wall_length(bounds, render_config):
    scene = SceneRenderer(bounds, render_config)
    facade = render_config.facade

    def panes(primitives):
        return [primitive for primitive in primitives if primitive.kind == "polygon"]

    one_storey = panes(scene._windows((0, 0), (12, 0), 3.0, temple=False))
    three_storeys = panes(scene._windows((0, 0), (12, 0), 9.0, temple=False))
    per_floor = int((12 - facade.window_spacing_m / 2) // facade.window_spacing_m)
    assert len(one_storey) == per_floor
    assert len(three_storeys) == 3 * per_floor
    assert scene._windows((0, 0), (1, 0), 9.0, temple=False) == []
    assert scene._windows((0, 0), (12, 0), 1.5, temple=False) == []


def test_gabled_roof_falls_back_for_irregular_footprints(bounds, render_config):
    scene = SceneRenderer(bounds, render_config)
    hall = scene.gabled(box(10, 10, 30, 18), 10.0, temple=True)
    assert hall is not None
    fills = {primitive.fill for primitive in hall}
    assert {"temple_trim"} <= fills
    assert fills & {"temple_roof", "temple_roof_dark"}
    l_shape = box(0, 0, 30, 6).union(box(0, 0, 6, 30))
    assert scene.gabled(l_shape, 10.0, temple=True) is None
    assert scene.gabled(box(0, 0, 20, 3), 10.0, temple=True) is None


def test_window_panes_have_a_highlight(bounds, render_config):
    scene = SceneRenderer(bounds, render_config)
    primitives = scene._windows((0, 0), (12, 0), 3.0, temple=False)
    lines = [primitive for primitive in primitives if primitive.kind == "line"]
    assert len(lines) == len(primitives) - len(lines)
    assert {line.outline for line in lines} == {"window_light"}


def test_shaded_edges_are_darker_than_their_fill(bounds, render_config):
    scene = SceneRenderer(bounds, render_config)
    fill = scene.color("building_wall_light")
    shade = scene.color("shade:building_wall_light")
    assert all(s < f for s, f in zip(shade[:3], fill[:3], strict=True))
    assert shade[3] == fill[3]


def test_landmark_forms_taper_to_a_point(bounds, render_config):
    scene = SceneRenderer(bounds, render_config)
    footprint = box(100, 50, 110, 60)
    for primitives in (scene.prang(footprint, 40.0), scene.chedi(footprint, 20.0)):
        polygons = [p for p in primitives if p.kind == "polygon"]
        assert polygons
        tops = [min(y for _, y in p.points) for p in polygons]
        top_pixel = scene.projection.world_to_native(105, 55, 0)[1]
        assert min(tops) < top_pixel
    prang_top = min(min(y for _, y in p.points) for p in scene.prang(footprint, 40.0) if p.points)
    apex = scene.projection.world_to_native(105, 55, 40.0)[1]
    assert abs(prang_top - apex) < 2
