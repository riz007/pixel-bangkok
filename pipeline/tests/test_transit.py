import numpy as np
import pytest
from shapely.geometry import LineString, box

from pixel_bangkok.blocks import read_region, render_blocks
from pixel_bangkok.normalise import normalise, transit_routes
from pixel_bangkok.render import SceneRenderer, composite, parse_color, render_layers


def _way(bounds, way_id, coords, tags):
    geometry = [
        {"lon": lon, "lat": lat} for lon, lat in (bounds.world_to_lonlat(x, y) for x, y in coords)
    ]
    return {"type": "way", "id": way_id, "tags": tags, "geometry": geometry}


@pytest.fixture
def transit(bounds, area, render_config):
    elements = [
        _way(
            bounds,
            1,
            [(0, 50), (120, 50)],
            {"railway": "subway", "bridge": "viaduct", "layer": "3", "name": "BTS"},
        ),
        _way(
            bounds,
            2,
            [(20, 20), (180, 20)],
            {"railway": "subway", "tunnel": "yes", "layer": "-2"},
        ),
        _way(bounds, 3, [(0, 80), (200, 80)], {"railway": "rail", "usage": "main"}),
        _way(
            bounds,
            4,
            [(60, 5), (150, 5)],
            {"highway": "motorway", "bridge": "yes", "layer": "1"},
        ),
        _way(bounds, 5, [(150, 5), (199, 5)], {"highway": "motorway"}),
        _way(
            bounds,
            6,
            [(100, 30), (100, 90)],
            {"highway": "residential", "bridge": "yes", "layer": "1"},
        ),
        {
            "type": "relation",
            "id": 9,
            "tags": {
                "type": "route",
                "route": "subway",
                "name:en": "BTS Sukhumvit Line (Kheha → Khu Khot)",
                "name": "สุขุมวิท",
                "colour": "#65B724",
            },
            "members": [{"type": "way", "ref": 1, "role": ""}],
        },
        {
            "type": "relation",
            "id": 8,
            "tags": {
                "type": "route",
                "route": "train",
                "name:en": "Train 379",
                "colour": "#FF9900",
            },
            "members": [{"type": "way", "ref": 1, "role": ""}],
        },
    ]
    layers, stats = normalise({"elements": elements}, area, render_config)
    by_id = {
        item["properties"]["source_id"]: item["properties"]
        for name in ("roads", "rail")
        for item in layers[name]
    }
    return by_id, stats


def test_rail_levels(transit):
    by_id, _ = transit
    assert by_id["way/1"]["level"] == "elevated"
    assert by_id["way/2"]["level"] == "underground"
    assert by_id["way/3"]["level"] == "ground"


def test_elevation_is_estimated_from_layer(transit, render_config):
    by_id, _ = transit
    bts = by_id["way/1"]
    assert bts["elevation_provenance"] == "estimated-layer"
    assert bts["elevation_m"] == max(
        render_config.transit.rail_min_elevation_m, 3 * render_config.transit.layer_height_m
    )
    assert "elevation_m" not in by_id["way/3"]


def test_metro_route_colour_beats_mainline_train(transit):
    by_id, _ = transit
    assert by_id["way/1"]["line"] == "BTS Sukhumvit Line"
    assert by_id["way/1"]["colour"] == "#65B724"
    assert by_id["way/1"]["line_source"] == "relation/9"


def test_only_expressway_bridges_are_elevated(transit):
    by_id, _ = transit
    assert by_id["way/4"]["elevated"] is True
    assert by_id["way/6"]["elevated"] is False
    assert by_id["way/6"]["bridge"] is True


def test_ramps_only_where_the_way_meets_the_network_at_grade(transit):
    by_id, _ = transit
    expressway = by_id["way/4"]
    assert expressway["ramp_end"] is True
    assert expressway["ramp_start"] is False
    bts = by_id["way/1"]
    assert bts["ramp_start"] is False
    assert bts["ramp_end"] is False


def test_route_without_colour_keeps_way_colour():
    lines = transit_routes(
        [
            {
                "type": "relation",
                "id": 1,
                "tags": {"type": "route", "route": "subway", "colour": "blue"},
                "members": [{"type": "way", "ref": 7}],
            }
        ]
    )
    assert lines[7]["colour"] is None


def _expressway(ramp_end=False):
    return (
        LineString([(20, 50), (180, 50)]),
        {
            "source_id": "way/4",
            "category": "motorway",
            "width_m": 14.0,
            "elevated": True,
            "elevation_m": 10.0,
            "ramp_start": False,
            "ramp_end": ramp_end,
            "part": 0,
        },
    )


def _bts():
    return (
        LineString([(100, 5), (100, 95)]),
        {
            "source_id": "way/1",
            "category": "subway",
            "level": "elevated",
            "tracks": 2,
            "track_width_m": 4.5,
            "elevation_m": 15.0,
            "part": 0,
        },
    )


def test_deck_is_drawn_at_its_elevation(bounds, render_config):
    scene = SceneRenderer(bounds, render_config)
    decks = scene.decks([_expressway()], [])
    buildings, _, _, _ = scene.buildings_and_vegetation([], [], decks)
    x, y = scene.projection.world_to_native(100, 50, 10.0)
    assert (
        buildings.getpixel((round(x), round(y)))[:3]
        == parse_color(render_config.palette["road_major"])[:3]
        or buildings.getpixel((round(x), round(y)))[:3]
        == parse_color(render_config.palette["road_marking"])[:3]
    )
    ground = scene.roads([_expressway()])
    gx, gy = scene.projection.world_to_native(60, 50, 0)
    assert ground.getpixel((round(gx), round(gy)))[3] == 0


def test_ramp_reaches_the_ground(bounds, render_config):
    scene = SceneRenderer(bounds, render_config)
    pieces = scene.decks([_expressway(ramp_end=True)], [])
    assert pieces[-1].z1 == 0.0
    assert pieces[0].z0 == 10.0
    assert all(a.z1 == b.z0 for a, b in zip(pieces, pieces[1:], strict=False))


def test_front_mask_holds_buildings_in_front_of_a_deck_only(bounds, render_config):
    scene = SceneRenderer(bounds, render_config)
    decks = scene.decks([], [_bts()])
    near = scene.projection.depth(110, 30) < scene.projection.depth(100, 30)
    front_x, back_x = (106, 85) if near else (85, 106)
    front_building = (
        box(front_x, 25, front_x + 8, 35),
        {"source_id": "way/10", "render_height_m": 30.0, "is_temple": False, "roof_shape": "flat"},
    )
    back_building = (
        box(back_x, 60, back_x + 8, 70),
        {"source_id": "way/11", "render_height_m": 30.0, "is_temple": False, "roof_shape": "flat"},
    )
    _, _, front, _ = scene.buildings_and_vegetation([front_building, back_building], [], decks)
    fx, fy = scene.projection.world_to_native(front_x + 4, 30, 25.0)
    bx, by = scene.projection.world_to_native(back_x + 4, 65, 25.0)
    assert front.getpixel((round(fx), round(fy)))[3] == 255
    assert front.getpixel((round(bx), round(by)))[3] == 0


def test_ground_and_underground_rail(bounds, render_config):
    scene = SceneRenderer(bounds, render_config)
    ground = (
        LineString([(0, 80), (200, 80)]),
        {"source_id": "way/3", "level": "ground", "tracks": 1, "track_width_m": 4.5},
    )
    tunnel = (
        LineString([(0, 20), (200, 20)]),
        {"source_id": "way/2", "level": "underground", "tracks": 2, "track_width_m": 4.5},
    )
    layer = scene.rail([ground, tunnel])
    pixels = np.asarray(layer)
    colours = {tuple(int(c) for c in p[:3]) for p in pixels[pixels[..., 3] > 0]}
    palette = render_config.palette
    for name in ("rail_bed", "rail_steel", "rail_sleeper", "subway_trace"):
        assert parse_color(palette[name])[:3] in colours


def test_blocks_match_whole_render_with_viaducts(tmp_path, bounds, render_config):
    layers = {
        "buildings": [],
        "trees": [],
        "water": [],
        "green": [],
        "roads": [_expressway(ramp_end=True)],
        "rail": [_bts()],
    }
    whole = composite(
        render_layers(bounds, render_config, layers),
        parse_color(render_config.palette["background"]),
    )
    info = render_blocks(bounds, render_config, layers, tmp_path, block_px=256)
    assembled = read_region(tmp_path, "render", (0, 0, info["width"], info["height"]), "RGB")
    assert (tmp_path / "front_0_0.png").exists()
    assert np.array_equal(np.asarray(whole), np.asarray(assembled))


def test_train_paths_ride_on_the_deck_and_skip_tunnels(render_config):
    from pixel_bangkok.motion import rail_paths

    nodes = {}

    def node(point):
        return nodes.setdefault(point, len(nodes))

    ramped = _bts()[1] | {"ramp_end": True, "colour": "#65B724", "line": "BTS Sukhumvit Line"}
    tunnel = {"source_id": "way/2", "level": "underground", "category": "subway"}
    ground = {
        "source_id": "way/3",
        "level": "ground",
        "category": "rail",
        "tracks": 1,
        "track_width_m": 4.5,
    }
    paths = rail_paths(
        [
            (LineString([(100, 5), (100, 395)]), ramped),
            (LineString([(0, 20), (200, 20)]), tunnel),
            (LineString([(0, 80), (200, 80)]), ground),
        ],
        render_config,
        node,
    )
    assert [path["id"] for path in paths] == ["way/1#0", "way/3#0"]
    bts, rail = paths
    assert bts["kind"] == "metro" and bts["colour"] == "#65B724"
    assert bts["points"][0][2] == 15.0
    assert bts["points"][-1][2] == 0.0
    assert all(point[2] == 0.0 for point in rail["points"])
    assert (
        max(abs(b[2] - a[2]) for a, b in zip(bts["points"], bts["points"][1:], strict=False))
        <= 12.0 * render_config.transit.ramp_grade + 1e-6
    )


def test_front_overlay_is_styled_tiled_and_listed_in_the_manifest(
    tmp_path, area, bounds, render_config
):
    import json

    from pixel_bangkok import pixelart, tile

    layers = {
        "buildings": [
            (
                box(106, 25, 114, 35),
                {
                    "source_id": "way/10",
                    "render_height_m": 30.0,
                    "is_temple": False,
                    "roof_shape": "flat",
                },
            )
        ],
        "trees": [],
        "water": [],
        "green": [],
        "roads": [],
        "rail": [_bts()],
    }
    build = tmp_path / "build"
    render_blocks(bounds, render_config, layers, build / "blocks", block_px=512)
    pixelart.run(render_config, build)
    assert (build / "blocks" / "front_overlay_0_0.png").exists()
    (tmp_path / "raw").mkdir()
    (tmp_path / "processed").mkdir()
    manifest_path = tile.run(area, render_config, tmp_path / "raw", tmp_path / "processed", build)
    manifest = json.loads(manifest_path.read_text())
    assert manifest["animation"]["front_url_template"].startswith("front/")
    assert (build / "front_overlay").is_dir()
    assert tile.PYRAMID_DIRS["front_overlay"] == "front"
