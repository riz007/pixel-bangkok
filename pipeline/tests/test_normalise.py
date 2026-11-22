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
        "building_parts": 1,
        "roads": 2,
        "rail": 0,
        "water": 2,
        "green": 1,
        "ground": 2,
        "trees": 1,
    }
    assert stats["skipped_duplicates"] == 1
    assert stats["skipped_outside_bounds"] == 1
    assert stats["building_parts_without_height"] == 1
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


def test_ground_categories(result):
    ground = _by_id(result[0]["ground"])
    assert ground["way/31"]["properties"]["category"] == "religious"
    assert ground["way/32"]["properties"]["category"] == "paved"
    assert "way/32" not in _by_id(result[0]["roads"])


def test_chunks_tile_the_area_exactly(bounds):
    from pixel_bangkok.extract import chunk_bounds

    chunks = chunk_bounds(bounds, chunk_m=60)
    assert len(chunks) == 4 * 2
    assert (
        sum(chunk.width_m * chunk.height_m for _, chunk in chunks)
        == bounds.width_m * bounds.height_m
    )
    assert min(chunk.origin_easting for _, chunk in chunks) == bounds.origin_easting
    assert (
        max(chunk.origin_easting + chunk.width_m for _, chunk in chunks)
        == bounds.origin_easting + bounds.width_m
    )


def test_chunk_payloads_merge_without_duplicates():
    from pixel_bangkok.extract import merge_elements

    first = {"elements": [{"type": "way", "id": 2}, {"type": "node", "id": 1}]}
    second = {"elements": [{"type": "way", "id": 2}, {"type": "way", "id": 3}]}
    assert [(e["type"], e["id"]) for e in merge_elements([first, second])] == [
        ("node", 1),
        ("way", 2),
        ("way", 3),
    ]


def test_palace_grounds_are_ground():
    from pixel_bangkok.normalise import _ground_category

    assert _ground_category({"historic": "castle", "name": "Grand Palace"}) == "palace"
    assert _ground_category({"historic": "memorial"}) is None


def test_building_parts_keep_only_sourced_vertical_extent():
    from pixel_bangkok.normalise import building_part

    assert building_part({"building:part": "yes", "height": "24"}) == {
        "category": "yes",
        "height_m": 24.0,
        "min_height_m": 0.0,
    }
    raised = building_part({"building:part": "yes", "height": "40", "min_height": "12"})
    assert raised["min_height_m"] == 12.0
    assert building_part({"building:part": "yes"})["height_m"] is None
    levels = building_part({"building:part": "yes", "height": "30", "building:min_level": "4"})
    assert levels["min_height_m"] is None
    inverted = building_part({"building:part": "yes", "height": "5", "min_height": "9"})
    assert inverted["height_m"] is None
    assert building_part({"building:part": "no", "height": "5"}) is None
