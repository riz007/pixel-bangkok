import json

import pytest

from pixel_bangkok.config import (
    REPO_ROOT,
    ConfigError,
    parse_area_config,
    parse_render_config,
)
from pixel_bangkok.projection import IsoProjection
from pixel_bangkok.publish import project_pois, write_index
from pixel_bangkok.schemas import PointOfInterest, SchemaError

from .conftest import AREA

CANOPY_SOURCE = {
    "dataset": "Canopy",
    "version": "v6",
    "resolution_m": 1.0,
    "licence": "CC BY 4.0",
    "attribution": "Tree canopy: X",
    "url": "https://example.invalid",
}


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
    raw = json.loads((REPO_ROOT / "config" / "render.json").read_text())
    with pytest.raises(ConfigError, match="missing 'trees'"):
        parse_render_config({key: value for key, value in raw.items() if key != "trees"})
    with pytest.raises(ConfigError, match="heights.min_height_m must be a number"):
        parse_render_config({**raw, "heights": {**raw["heights"], "min_height_m": "3"}})
    with pytest.raises(ConfigError, match="resolution_m must be positive"):
        parse_area_config(
            {**AREA, "rasters": {"tree_canopy": {**CANOPY_SOURCE, "resolution_m": 0}}}
        )
    area = parse_area_config({**AREA, "rasters": {"tree_canopy": CANOPY_SOURCE}})
    assert area.tree_canopy is not None and area.building_heights is None
    assert render_config.pixels_per_metre >= 1
    assert render_config.tiles.format in {"webp", "png"}


def test_thumbnails_are_cropped_from_blocks(tmp_path):
    from PIL import Image

    from pixel_bangkok.blocks import block_grid
    from pixel_bangkok.publish import THUMBNAIL_SIZE, write_thumbnails

    blocks_dir = tmp_path / "blocks"
    blocks_dir.mkdir()
    blocks = block_grid(800, 600, 512)
    for block in blocks:
        Image.new("RGB", (block.width, block.height), (10, 200, 30)).save(
            blocks_dir / f"master_{block.name}.png"
        )
    (blocks_dir / "blocks.json").write_text(
        json.dumps(
            {"width": 800, "height": 600, "block_px": 512, "blocks": [b.__dict__ for b in blocks]}
        )
    )
    pois = [{"id": "temple", "image": {"x": 512.4, "y": 300.0}}]
    assert write_thumbnails(pois, tmp_path, tmp_path / "places") == 1
    assert pois[0]["thumbnail"] == "places/temple.webp"
    with Image.open(tmp_path / "places" / "temple.webp") as thumb:
        assert thumb.size == THUMBNAIL_SIZE
    assert write_thumbnails(pois, tmp_path / "missing", tmp_path / "x") == 0
