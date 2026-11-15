import json

import pytest

from pixel_bangkok.config import ConfigError, parse_area_config, parse_render_config
from pixel_bangkok.projection import IsoProjection
from pixel_bangkok.publish import project_pois, write_index
from pixel_bangkok.schemas import PointOfInterest, SchemaError

from .conftest import AREA


def _poi(bounds, x, y, poi_id="p"):
    lon, lat = bounds.world_to_lonlat(x, y)
    return PointOfInterest.from_dict(
        {
            "id": poi_id,
            "name_en": "Test",
            "name_th": "ทดสอบ",
            "category": "landmark",
            "lon": lon,
            "lat": lat,
            "description": "A test point.",
        }
    )


def test_poi_image_coordinates_use_the_render_projection(bounds, render_config):
    projection = IsoProjection.create(bounds, render_config)
    published = project_pois([_poi(bounds, 50, 50)], bounds, projection)
    expected = projection.world_to_master(50, 50)
    assert (published[0]["image"]["x"], published[0]["image"]["y"]) == pytest.approx(
        expected, abs=0.02
    )
    assert published[0]["name_th"] == "ทดสอบ"
    assert 0 <= published[0]["image"]["x"] <= projection.master_width


def test_pois_outside_bounds_are_not_published(bounds, render_config):
    projection = IsoProjection.create(bounds, render_config)
    pois = [_poi(bounds, 50, 50, "in"), _poi(bounds, 500, 50, "out")]
    assert [poi["id"] for poi in project_pois(pois, bounds, projection)] == ["in"]


def test_poi_validation():
    with pytest.raises(SchemaError, match="missing"):
        PointOfInterest.from_dict({"id": "x"})
    with pytest.raises(SchemaError, match="category"):
        PointOfInterest.from_dict(
            {"id": "x", "name_en": "X", "category": "?", "lon": 1, "lat": 1, "description": ""}
        )
    with pytest.raises(SchemaError, match="lon/lat"):
        PointOfInterest.from_dict(
            {
                "id": "x",
                "name_en": "X",
                "category": "pier",
                "lon": 661066,
                "lat": 1519878,
                "description": "",
            }
        )


def test_index_lists_published_areas(tmp_path):
    for area_id in ("b-area", "a-area"):
        (tmp_path / area_id).mkdir()
        (tmp_path / area_id / "manifest.json").write_text(
            json.dumps({"area_id": area_id, "name": {"en": area_id, "th": None}})
        )
    index = json.loads(write_index(tmp_path).read_text())
    assert [entry["id"] for entry in index["areas"]] == ["a-area", "b-area"]


def test_config_validation(render_config):
    with pytest.raises(ConfigError, match="width_m"):
        parse_area_config({**AREA, "width_m": 0})
    with pytest.raises(ConfigError, match="missing 'crs'"):
        parse_area_config({key: value for key, value in AREA.items() if key != "crs"})
    with pytest.raises(ConfigError, match="missing 'camera'"):
        parse_render_config({})
    assert render_config.pixels_per_metre >= 1
    assert render_config.tiles.format in {"webp", "png"}
