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
    assert manifest["version"] == 3
    assert manifest["attributions"] == [
        {
            "text": area.source.attribution,
            "url": area.source.attribution_url,
            "licence": area.source.licence,
            "provider": area.source.provider,
        }
    ]
    assert manifest["source"]["retrieved_at"] == "2026-01-01T00:00:00+00:00"


def test_manifest_rejects_master_that_does_not_match_config(area, render_config):
    with pytest.raises(ValueError, match="re-run"):
        build_manifest(area, render_config, (10, 10), level_dimensions(10, 10), "abc", {})


def test_master_size_matches_manifest_projection(bounds, render_config):
    projection = IsoProjection.create(bounds, render_config)
    native = Image.new("RGB", (projection.native_width, projection.native_height))
    master = apply_pixel_art(native, render_config)
    assert master.size == (projection.master_width, projection.master_height)


def test_manifest_credits_raster_sources_that_were_used(render_config):
    import dataclasses

    from pixel_bangkok.config import RasterSourceConfig, parse_area_config

    from .conftest import AREA

    raster = RasterSourceConfig("Heights", "v1", 0.5, "CC BY 4.0", "Heights: X", "https://x", 2023)
    area = dataclasses.replace(parse_area_config(AREA), building_heights=raster)
    from pixel_bangkok.crs import MapBounds

    projection = IsoProjection.create(MapBounds.from_area(area), render_config)
    size = (projection.master_width, projection.master_height)
    levels = level_dimensions(*size)
    unused = build_manifest(area, render_config, size, levels, "abc", {})
    used = build_manifest(area, render_config, size, levels, "abc", {}, ("building_heights",))
    assert len(unused["attributions"]) == 1
    assert used["attributions"][1] == {
        "text": "Heights: X",
        "url": "https://x",
        "licence": "CC BY 4.0",
        "provider": "Heights",
    }


def test_box_pool_averages_and_ignores_transparent_colour():
    import numpy as np

    from pixel_bangkok.tile import _pack, _unpack, box_pool

    image = Image.new("RGBA", (2, 2), (200, 0, 0, 255))
    image.putpixel((1, 1), (0, 0, 200, 255))
    pooled = _unpack(box_pool(_pack(image)), "RGBA")
    assert pooled.getpixel((0, 0)) == (150, 0, 50, 255)
    overlay = Image.new("RGBA", (2, 2), (0, 255, 0, 0))
    overlay.putpixel((0, 0), (200, 100, 50, 255))
    pooled = _unpack(box_pool(_pack(overlay)), "RGBA")
    assert pooled.getpixel((0, 0)) == (200, 100, 50, 64)
    assert box_pool(np.zeros((3, 5), dtype=np.uint32)).shape == (2, 3)


def test_lower_levels_blend_fine_patterns(tmp_path):
    master = Image.new("RGB", (300, 200), (200, 0, 0))
    for x in range(0, 300, 2):
        for y in range(200):
            master.putpixel((x, y), (0, 0, 200))
    tiles = TileConfig(tile_size=128, overlap=0, format="png", lossless=True)
    levels = write_pyramid(master, tmp_path / "tiles", tiles)
    with Image.open(tmp_path / "tiles" / str(levels[-2]["level"]) / "0_0.png") as tile:
        assert tile.convert("RGB").getpixel((5, 5)) == (100, 0, 100)


def test_no_pyramid_is_written_into_working_folders():
    from pixel_bangkok.tile import PYRAMID_DIRS

    assert not set(PYRAMID_DIRS) & {"ai", "blocks", "layers"}
    assert not any(name.startswith("ai") for name in PYRAMID_DIRS.values())


def test_blank_tiles_are_not_written_and_presence_is_recorded(tmp_path):
    import base64
    import json

    import numpy as np

    master = Image.new("RGB", (512, 256), (28, 20, 18))
    master.paste((200, 100, 50), (0, 0, 100, 100))
    tiles = TileConfig(tile_size=128, overlap=0, format="png", lossless=True)
    blank = 28 | (20 << 8) | (18 << 16) | (255 << 24)
    from pixel_bangkok.tile import write_pyramid_blocks

    levels = write_pyramid_blocks(
        [((0, 0), lambda: master)], 512, 256, "RGB", tmp_path / "t", tiles, tmp_path / "w", blank
    )
    top = levels[-1]["level"]
    assert (tmp_path / "t" / str(top) / "0_0.png").exists()
    assert not (tmp_path / "t" / str(top) / "3_1.png").exists()
    present = json.loads((tmp_path / "t" / "present.json").read_text())
    bits = np.unpackbits(
        np.frombuffer(base64.b64decode(present[str(top)]), np.uint8), bitorder="little"
    )
    assert bits[0] == 1 and bits.sum() == 1


def test_transparent_overlay_tiles_are_not_written(tmp_path):
    overlay = Image.new("RGBA", (256, 128), (0, 0, 0, 0))
    overlay.paste((10, 20, 30, 255), (0, 0, 10, 10))
    tiles = TileConfig(tile_size=128, overlap=0, format="png", lossless=True)
    levels = write_pyramid(overlay, tmp_path / "o", tiles)
    top = levels[-1]["level"]
    assert (tmp_path / "o" / str(top) / "0_0.png").exists()
    assert not (tmp_path / "o" / str(top) / "1_0.png").exists()
