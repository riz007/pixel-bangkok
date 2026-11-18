import numpy as np
import pytest
from shapely.geometry import box

from pixel_bangkok.heights import (
    RasterSample,
    derive_height,
    parse_height_m,
    parse_levels,
    roof_shape,
    sample_raster_height,
)
from pixel_bangkok.rasters import AreaGrid, RasterLayer


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("12", 12.0),
        ("12.5 m", 12.5),
        ("7,5m", 7.5),
        ("40 ft", 12.192),
        ("30'", 9.144),
        ("tall", None),
        ("0", None),
        ("-3", None),
        (None, None),
    ],
)
def test_parse_height(raw, expected):
    assert parse_height_m(raw) == (pytest.approx(expected) if expected else None)


def test_parse_levels():
    assert parse_levels("3") == 3
    assert parse_levels("2.5") == 2.5
    assert parse_levels("many") is None


def test_source_height_wins_over_levels(render_config):
    derived = derive_height("20", "2", render_config.heights)
    assert (derived.render_height_m, derived.provenance) == (20.0, "source")
    assert derived.height_source == "osm-height"


def test_levels_are_marked_estimated(render_config):
    derived = derive_height(None, "4", render_config.heights)
    floor = render_config.heights.floor_height_m
    assert (derived.render_height_m, derived.provenance) == (4 * floor, "estimated")
    assert derived.height_source == "osm-levels"
    assert "assumed" in derived.note


def test_osm_levels_win_over_raster(render_config):
    raster = RasterSample(14.0, 100, "raster")
    derived = derive_height(None, "2", render_config.heights, raster=raster)
    assert derived.height_source == "osm-levels"


def test_raster_estimate_is_marked_estimated_and_clamped(render_config):
    config = render_config.heights
    derived = derive_height(None, None, config, raster=RasterSample(11.5, 80, "Test 2023"))
    assert (derived.render_height_m, derived.provenance, derived.height_source) == (
        11.5,
        "estimated",
        "raster",
    )
    assert "Test 2023" in derived.note and "80 pixels" in derived.note
    low = derive_height(None, None, config, raster=RasterSample(1.0, 80, "Test 2023"))
    assert low.render_height_m == config.min_height_m
    assert "raised from 1 m" in low.note


def test_missing_data_is_unknown_not_estimated(render_config):
    derived = derive_height("tall", None, render_config.heights)
    assert (derived.render_height_m, derived.provenance) == (
        render_config.heights.unknown_height_m,
        "unknown",
    )
    assert derived.height_source is None


def test_manual_override_is_marked_manual(render_config):
    derived = derive_height("20", "2", render_config.heights, {"height_m": 76, "note": "curated"})
    assert (derived.render_height_m, derived.provenance, derived.note) == (
        76.0,
        "manual",
        "curated",
    )


def _height_layer(bounds, height_value, presence_value):
    grid = AreaGrid.for_bounds(bounds, 0.5)
    heights = np.zeros((grid.height, grid.width), dtype=np.float32)
    presence = np.zeros_like(heights)
    rows = slice(grid.height - 40, grid.height - 20)
    columns = slice(20, 40)
    heights[rows, columns] = height_value
    presence[rows, columns] = presence_value
    heights[grid.height - 40, 20] = 30.0
    return RasterLayer(
        np.stack([heights, presence]),
        grid.transform,
        grid.crs,
        ("building_height", "building_presence"),
    )


def test_raster_sampling_uses_pixels_inside_the_footprint(bounds, render_config):
    layer = _height_layer(bounds, 9.0, 0.9)
    sample = sample_raster_height(layer, box(10, 10, 20, 20), bounds, render_config.heights, "t")
    assert sample is not None
    assert sample.height_m == 9.0
    assert sample.pixels == 400
    assert (
        sample_raster_height(layer, box(50, 50, 60, 60), bounds, render_config.heights, "t") is None
    )


def test_raster_sampling_ignores_low_presence(bounds, render_config):
    layer = _height_layer(bounds, 9.0, 0.2)
    assert (
        sample_raster_height(layer, box(10, 10, 20, 20), bounds, render_config.heights, "t") is None
    )


def test_roof_shapes():
    assert roof_shape({"is_tower": True, "category": "temple"}, None) == "spire"
    tower = {"is_tower": True, "category": "yes", "tower_type": "pagoda"}
    assert roof_shape(tower, None) == "chedi"
    assert roof_shape({**tower, "tower_type": "stupa"}, None) == "chedi"
    assert roof_shape({**tower, "tower_type": "communication"}, None) == "spire"
    assert roof_shape(tower, {"roof_shape": "prang"}) == "prang"
    assert roof_shape({"is_tower": False, "category": "temple"}, None) == "gabled"
    assert roof_shape({"is_tower": False, "category": "yes"}, None) == "flat"
    assert roof_shape({"is_tower": False, "category": "yes"}, {"roof_shape": "spire"}) == "spire"


def test_implausible_osm_values_fall_back_with_a_note(render_config):
    from pixel_bangkok.heights import derive_height

    derived = derive_height(None, "12345678910111212", render_config.heights)
    assert derived.render_height_m == render_config.heights.unknown_height_m
    assert "implausible" in derived.note
    assert derive_height("9000 m", None, render_config.heights).height_source != "osm-height"
