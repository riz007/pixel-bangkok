import json

import pytest
from PIL import Image

from pixel_bangkok.config import TileConfig
from pixel_bangkok.pixelart import apply_pixel_art
from pixel_bangkok.projection import IsoProjection
from pixel_bangkok.tile import build_manifest, level_dimensions, tile_box, write_pyramid


def test_level_dimensions_for_non_square_image():
    levels = level_dimensions(1000, 300)
    assert levels[-1] == {"level": 10, "width": 1000, "height": 300}
    assert levels[-2] == {"level": 9, "width": 500, "height": 150}
    assert levels[0] == {"level": 0, "width": 1, "height": 1}


def test_tile_box_handles_overlap_and_edges():
    assert tile_box(0, 0, 1000, 300, 256, 1) == (0, 0, 257, 257)
    assert tile_box(1, 0, 1000, 300, 256, 1) == (255, 0, 513, 257)
    assert tile_box(3, 1, 1000, 300, 256, 1) == (767, 255, 1000, 300)


@pytest.mark.parametrize("overlap", [0, 1])
def test_pyramid_reassembles_to_master(tmp_path, overlap):
    master = Image.new("RGB", (700, 300))
    master.putdata([(x % 256, y % 256, (x * y) % 256) for y in range(300) for x in range(700)])
    tiles = TileConfig(tile_size=256, overlap=overlap, format="png", lossless=True)
    levels = write_pyramid(master, tmp_path / "tiles", tiles)
    top = levels[-1]
    assert (top["columns"], top["rows"]) == (3, 2)
    rebuilt = Image.new("RGB", master.size)
    for column in range(top["columns"]):
        for row in range(top["rows"]):
            with Image.open(tmp_path / "tiles" / str(top["level"]) / f"{column}_{row}.png") as tile:
                left, upper, right, lower = tile_box(column, row, 700, 300, 256, overlap)
                assert tile.size == (right - left, lower - upper)
                rebuilt.paste(tile, (left, upper))
    assert rebuilt.tobytes() == master.tobytes()
    assert (tmp_path / "tiles" / "0" / "0_0.png").exists()


def test_manifest_describes_image_tiles_and_projection(area, bounds, render_config):
    projection = IsoProjection.create(bounds, render_config)
    size = (projection.master_width, projection.master_height)
    levels = level_dimensions(*size)
    manifest = build_manifest(
        area, render_config, size, levels, "abc", {"retrieved_at": "2026-01-01T00:00:00+00:00"}
    )
    json.dumps(manifest)
    assert manifest["image"] == {"width": size[0], "height": size[1]}
    assert manifest["tiles"]["tile_size"] == render_config.tiles.tile_size
    assert manifest["tiles"]["overlap"] == render_config.tiles.overlap
    assert manifest["tiles"]["max_level"] == levels[-1]["level"]
    assert manifest["projection"]["world_to_image"] == projection.master_matrix()
    assert manifest["projection"]["bounds"]["crs"] == "EPSG:32647"
    assert manifest["attribution"]["text"] == area.source.attribution
    assert manifest["source"]["retrieved_at"] == "2026-01-01T00:00:00+00:00"


def test_manifest_rejects_master_that_does_not_match_config(area, render_config):
    with pytest.raises(ValueError, match="re-run"):
        build_manifest(area, render_config, (10, 10), level_dimensions(10, 10), "abc", {})


def test_master_size_matches_manifest_projection(bounds, render_config):
    projection = IsoProjection.create(bounds, render_config)
    native = Image.new("RGB", (projection.native_width, projection.native_height))
    master = apply_pixel_art(native, render_config)
    assert master.size == (projection.master_width, projection.master_height)
