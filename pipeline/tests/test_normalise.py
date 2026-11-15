import pytest
from shapely.geometry import shape

from pixel_bangkok.normalise import normalise


@pytest.fixture
def result(raw_osm, area, render_config):
    return normalise(raw_osm, area, render_config)


def _by_id(features):
    return {item["properties"]["source_id"]: item for item in features}


def test_layers_and_counts(result):
    layers, stats = result
    assert {name: len(items) for name, items in layers.items()} == {
        "buildings": 5,
        "roads": 2,
        "water": 2,
        "green": 1,
        "trees": 1,
    }
    assert stats["skipped_duplicates"] == 1
    assert stats["skipped_outside_bounds"] == 1
    assert stats["skipped_building_parts"] == 1
    assert stats["skipped_unclassified"] == 2
    assert stats["repaired_invalid"] == 1


def test_source_ids_and_tags_are_preserved(result):
    buildings = _by_id(result[0]["buildings"])
    assert buildings["way/1"]["properties"]["source_height"] == "12"
    assert buildings["way/2"]["properties"]["source_levels"] == "2"
    assert buildings["way/2"]["properties"]["is_temple"] is True
    assert buildings["way/3"]["properties"]["is_tower"] is True
    assert "render_height_m" not in buildings["way/1"]["properties"]


def test_features_are_clipped_to_bounds(result, bounds):
    layers, _ = result
    for features in layers.values():
        for item in features:
            world = bounds.geometry_to_world(shape(item["geometry"]))
            min_x, min_y, max_x, max_y = world.bounds
            assert min_x >= -0.01 and min_y >= -0.01
            assert max_x <= bounds.width_m + 0.01 and max_y <= bounds.height_m + 0.01
    buildings = _by_id(layers["buildings"])
    assert buildings["way/5"]["properties"]["clipped"] is True
    assert buildings["way/1"]["properties"]["clipped"] is False


def test_widths_record_provenance(result):
    roads = _by_id(result[0]["roads"])
    assert roads["way/10"]["properties"]["width_provenance"] == "estimated"
    assert roads["way/11"]["properties"]["width_m"] == 3
    assert roads["way/11"]["properties"]["width_provenance"] == "source"


def test_river_centre_lines_are_not_rendered_as_water(result):
    assert set(_by_id(result[0]["water"])) == {"way/20", "way/21"}
