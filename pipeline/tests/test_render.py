import io

import pytest
from shapely.affinity import translate
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

    scene_renderer = SceneRenderer(bounds, render_config)
    material = scene_renderer.material(
        box(40, 40, 60, 60), {"render_height_m": 12.0, "source_id": "way/1"}
    )
    roof_colours = {
        scene_renderer.color(name)[:3]
        for name in (
            f"{material}_roof",
            "rooftop_tank_roof",
            "rooftop_unit_roof",
            "shade:rooftop_tank_roof",
            "shade:rooftop_unit_roof",
        )
    }
    assert pixel(50, 50, 12) in roof_colours
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
    colour_budget = 2 * (len(render_config.palette) + 5 * len(render_config.materials))
    assert unique_colors(master) <= colour_budget
    projection = IsoProjection.create(bounds, render_config)
    px, py = projection.world_to_master(100, 11.5)
    road = parse_color(render_config.palette["road"])[:3]
    assert master.getpixel((round(px), round(py))) == road
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
    buildings, vegetation, _, _ = scene.buildings_and_vegetation([_building()], [behind, in_front])

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

    one_storey = panes(scene._windows((0, 0), (12, 0), 3.0, skin="building"))
    three_storeys = panes(scene._windows((0, 0), (12, 0), 9.0, skin="building"))
    per_floor = int((12 - facade.window_spacing_m / 2) // facade.window_spacing_m)
    assert len(one_storey) == per_floor
    assert len(three_storeys) == 3 * per_floor
    assert scene._windows((0, 0), (1, 0), 9.0, skin="building") == []
    assert scene._windows((0, 0), (12, 0), 1.5, skin="building") == []


def test_gabled_roof_falls_back_for_irregular_footprints(bounds, render_config):
    scene = SceneRenderer(bounds, render_config)
    hall = scene.gabled(box(10, 10, 30, 18), 10.0, skin="temple")
    assert hall is not None
    fills = {primitive.fill for primitive in hall}
    assert {"temple_trim"} <= fills
    assert fills & {"temple_roof", "temple_roof_dark"}
    l_shape = box(0, 0, 30, 6).union(box(0, 0, 6, 30))
    assert scene.gabled(l_shape, 10.0, skin="temple") is None
    assert scene.gabled(box(0, 0, 20, 3), 10.0, skin="temple") is None


def test_window_panes_have_a_highlight(bounds, render_config):
    scene = SceneRenderer(bounds, render_config)
    primitives = scene._windows((0, 0), (12, 0), 3.0, skin="building")
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


def test_materials_are_deterministic_and_follow_building_size(bounds, render_config):
    scene = SceneRenderer(bounds, render_config)
    groups = render_config.material_groups
    small = box(0, 0, 10, 10)
    big = box(0, 0, 40, 40)
    assert (
        scene.material(small, {"render_height_m": 5.0, "source_id": "way/9"}) in groups["lowrise"]
    )
    assert scene.material(big, {"render_height_m": 12.0, "source_id": "way/9"}) in groups["general"]
    assert scene.material(big, {"render_height_m": 60.0, "source_id": "way/9"}) in groups["tower"]
    first = scene.material(big, {"render_height_m": 12.0, "source_id": "way/42"})
    assert first == scene.material(big, {"render_height_m": 12.0, "source_id": "way/42"})
    picks = {
        scene.material(big, {"render_height_m": 12.0, "source_id": f"way/{i}"}) for i in range(40)
    }
    assert len(picks) > 3


def test_rooftop_items_sit_inside_the_roof_and_only_on_tall_buildings(bounds, render_config):
    scene = SceneRenderer(bounds, render_config)
    roof = box(10, 10, 30, 30)
    assert scene._rooftop_items(roof, 4.0, "way/1") == []
    items = scene._rooftop_items(roof, 15.0, "way/1")
    assert items
    assert items == scene._rooftop_items(roof, 15.0, "way/1")
    corners = [scene.projection.world_to_native(x, y, 15.0) for x in (10, 30) for y in (10, 30)]
    xs = [x for primitive in items for x, _ in primitive.points]
    assert min(xs) >= min(c[0] for c in corners) - 1
    assert max(xs) <= max(c[0] for c in corners) + 1


def test_metal_roofs_get_corrugation(bounds, render_config):
    scene = SceneRenderer(bounds, render_config)
    footprint = box(10, 10, 20, 16)
    metal = scene.prism(footprint, 5.0, "metal_rust", "way/3")
    flat = scene.prism(footprint, 5.0, "concrete_grey", "way/3")
    corrugation = [p for p in metal if p.kind == "line" and p.outline == "shade:metal_rust_roof"]
    assert len(corrugation) >= 5
    assert not [p for p in flat if p.outline == "shade:concrete_grey_roof"]


def test_buildings_in_temple_grounds_are_drawn_traditionally(bounds, render_config):
    scene = SceneRenderer(bounds, render_config)
    hall = box(20, 20, 40, 30)
    plain = {
        "render_height_m": 9.0,
        "source_id": "way/77",
        "is_temple": False,
        "roof_shape": "flat",
    }
    outside = {p.fill for p in scene.building(hall, plain)}
    scene.set_precincts([(box(10, 10, 50, 50), {"category": "religious"})])
    inside = {p.fill for p in scene.building(hall, plain)}
    assert "temple_trim" not in outside
    assert {"temple_trim"} <= inside
    assert inside & {"temple_roof", "temple_roof_dark"}


def test_building_parts_replace_the_outline_only_when_all_heights_are_known(bounds, render_config):
    from pixel_bangkok.render import parts_by_building

    outline = box(0, 0, 20, 20)
    building = (outline, {"source_id": "way/1"})
    plinth = (box(0, 0, 20, 20), {"source_id": "way/2", "height_m": 1.0, "min_height_m": 0.0})
    wing = (box(1, 1, 3, 3), {"source_id": "way/3", "height_m": 24.0, "min_height_m": 0.0})
    grouped = parts_by_building([building], [plinth, wing])
    assert [part["source_id"] for _, part in grouped["way/1"]] == ["way/2", "way/3"]
    assert list(parts_by_building([building], [wing])) == ["way/1"]
    unknown = (box(5, 5, 9, 9), {"source_id": "way/4", "height_m": None, "min_height_m": 0.0})
    assert parts_by_building([building], [wing, unknown]) == {}


def test_parts_are_drawn_to_their_own_heights(bounds, render_config):
    scene = SceneRenderer(bounds, render_config)
    outline = box(100, 50, 120, 70)
    properties = {
        "source_id": "way/1",
        "is_temple": False,
        "category": "yes",
        "render_height_m": 8.0,
    }
    parts = [
        (box(100, 50, 120, 70), {"source_id": "way/2", "height_m": 1.0, "min_height_m": 0.0}),
        (box(101, 51, 104, 54), {"source_id": "way/3", "height_m": 24.0, "min_height_m": 0.0}),
        (box(110, 60, 114, 64), {"source_id": "way/4", "height_m": 9.0, "min_height_m": 6.0}),
    ]
    primitives = scene.building_parts(outline, parts, properties)
    top = min(y for p in primitives for _, y in p.points) if primitives else None
    assert top is not None
    assert abs(top - scene.projection.world_to_native(101, 54, 24.0)[1]) < 30
    floating = [p for p in primitives if p.kind == "polygon" and p.points and len(p.points) == 4]
    assert floating


def test_a_plinth_is_drawn_before_the_turret_standing_on_it(bounds, render_config):
    scene = SceneRenderer(bounds, render_config)
    properties = {"source_id": "way/1", "is_temple": False, "category": "yes"}
    properties |= {"render_height_m": 8.0, "facade": "plain"}
    plinth = Point(110, 60).buffer(12)
    turret = Point(110, 60).buffer(3.5)
    parts = [
        (turret, {"source_id": "way/2", "height_m": 7.0, "min_height_m": 0.0}),
        (plinth, {"source_id": "way/3", "height_m": 1.0, "min_height_m": 0.0}),
    ]
    primitives = scene.building_parts(plinth, parts, properties)
    tops = [p.z for p in primitives if p.kind == "area"]
    assert tops[0] == 1.0 and tops[-1] == 7.0
    assert not any(p.fill and "window" in p.fill for p in primitives)


def test_lit_windows_sit_on_drawn_windows_and_repeat_every_render(bounds, render_config):
    scene = SceneRenderer(bounds, render_config)
    polygon, properties = _building()
    tall = properties | {"render_height_m": 24.0}
    primitives = scene.building(polygon, tall)
    windows = {
        primitive.points
        for primitive in primitives
        if primitive.kind == "polygon" and (primitive.fill or "").endswith("window")
    }
    lit = scene.lit_windows(primitives, tall["source_id"])
    assert 0 < len(lit) < len(windows)
    assert {primitive.points for primitive in lit} <= windows
    assert {primitive.fill for primitive in lit} <= {"window_lit", "window_lit_soft"}
    again = scene.lit_windows(scene.building(polygon, tall), tall["source_id"])
    assert [primitive.points for primitive in again] == [primitive.points for primitive in lit]


def test_lit_windows_are_hidden_by_what_stands_in_front(bounds, render_config):
    scene = SceneRenderer(bounds, render_config)
    polygon, properties = _building()
    tall = properties | {"render_height_m": 24.0}
    _, _, _, open_view = scene.buildings_and_vegetation([(polygon, tall)], [])
    lit = scene.lit_windows(scene.building(polygon, tall), tall["source_id"])
    pixels = [
        (round(sum(x for x, _ in p.points) / 4), round(sum(y for _, y in p.points) / 4))
        for p in lit
    ]
    assert any(open_view.getpixel(pixel)[3] == 255 for pixel in pixels)
    # A tall building right in front of the facade hides its lights.
    blocker = (
        translate(polygon, 14, -14),
        tall | {"source_id": "way/front", "render_height_m": 40.0},
    )
    _, _, _, hidden = scene.buildings_and_vegetation([(polygon, tall), blocker], [])
    shown = sum(hidden.getpixel(pixel)[3] == 255 for pixel in pixels)
    assert shown < sum(open_view.getpixel(pixel)[3] == 255 for pixel in pixels)
