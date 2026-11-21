import numpy as np
from PIL import Image

from pixel_bangkok.motion import build_paths, classify
from pixel_bangkok.pixelart import overlay_from_mask


def _way(bounds, way_id, coords, tags):
    return {
        "type": "way",
        "id": way_id,
        "tags": tags,
        "geometry": [
            {"lon": lon, "lat": lat}
            for lon, lat in (bounds.world_to_lonlat(x, y) for x, y in coords)
        ],
    }


def test_classification():
    assert classify({"highway": "primary"}) == ("roads", "major")
    assert classify({"highway": "primary_link"}) == ("roads", "major")
    assert classify({"highway": "residential"}) == ("roads", "minor")
    assert classify({"highway": "service"}) == ("roads", "service")
    assert classify({"highway": "service", "service": "parking_aisle"}) is None
    assert classify({"highway": "footway"}) == ("footways", "footway")
    assert classify({"highway": "pedestrian"}) == ("footways", "pedestrian")
    assert classify({"highway": "steps"}) == ("footways", "steps")
    assert classify({"highway": "pedestrian", "area": "yes"}) is None
    assert classify({"highway": "footway", "tunnel": "yes"}) is None
    assert classify({"highway": "footway", "indoor": "yes"}) is None
    assert classify({"highway": "corridor"}) is None
    assert classify({"highway": "residential", "access": "private"}) is None
    assert classify({"waterway": "river"}) == ("waterways", "river")
    assert classify({"waterway": "canal"}) == ("waterways", "canal")
    assert classify({"route": "ferry"}) == ("waterways", "ferry")


def test_paths_are_clipped_connected_and_keep_direction(bounds, render_config):
    elements = [
        _way(bounds, 1, [(-50, 20), (100, 20)], {"highway": "primary"}),
        _way(bounds, 2, [(100, 20), (100, 80)], {"highway": "residential", "oneway": "yes"}),
        _way(bounds, 3, [(100, 80), (100, 20)], {"highway": "residential", "oneway": "-1"}),
        _way(bounds, 4, [(0, 90), (200, 90)], {"waterway": "river"}),
        _way(bounds, 5, [(10, 10), (12, 10)], {"highway": "residential"}),
        _way(bounds, 6, [(0, 50), (50, 50)], {"highway": "footway"}),
    ]
    paths = build_paths(elements, bounds, render_config)
    roads = {path["id"]: path for path in paths["roads"]}
    assert set(roads) == {"way/1", "way/2", "way/3"}
    footways = paths["footways"]
    assert [path["id"] for path in footways] == ["way/6"]
    assert footways[0]["oneway"] == 0
    assert footways[0]["width_m"] == render_config.road_widths_m["footway"]
    assert paths["sidewalk_m"] == render_config.sidewalk_m
    assert roads["way/1"]["points"][0][0] == 0.0
    assert roads["way/1"]["end"] == roads["way/2"]["start"]
    assert roads["way/2"]["oneway"] == 1 and roads["way/3"]["oneway"] == -1
    assert roads["way/1"]["width_m"] == render_config.road_widths_m["primary"]
    assert [path["kind"] for path in paths["waterways"]] == ["river"]
    assert paths["drive_side"] == "left"


def test_overlay_keeps_masked_pixels_only():
    mask = np.zeros((2, 4), dtype=bool)
    mask[0, 0] = True
    mask[1, 3] = True
    master = Image.new("RGB", (4, 2), (90, 90, 90))
    overlay = np.asarray(overlay_from_mask(master, mask))
    assert overlay[0, 0].tolist() == [90, 90, 90, 255]
    assert overlay[1, 3].tolist() == [90, 90, 90, 255]
    assert overlay[0, 1, 3] == 0 and overlay[1, 0, 3] == 0


def test_elevated_expressways_are_not_ground_traffic():
    from pixel_bangkok.motion import classify

    assert classify({"highway": "motorway", "bridge": "yes", "layer": "2"}) is None
    assert classify({"highway": "primary", "bridge": "viaduct"}) is None
    assert classify({"highway": "primary", "bridge": "yes"}) is not None
