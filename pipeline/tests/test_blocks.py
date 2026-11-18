import numpy as np
from PIL import Image

from pixel_bangkok.blocks import (
    block_grid,
    ground_window,
    read_region,
    render_blocks,
    screen_to_ground,
)
from pixel_bangkok.config import TileConfig
from pixel_bangkok.projection import IsoProjection
from pixel_bangkok.render import composite, parse_color, render_layers
from pixel_bangkok.tile import write_pyramid, write_pyramid_blocks

from .test_render import scene  # noqa: F401


def test_grid_covers_image_without_overlap():
    blocks = block_grid(1000, 300, 256)
    assert len(blocks) == 4 * 2
    assert sum(b.width * b.height for b in blocks) == 1000 * 300
    assert blocks[-1].width == 1000 - 3 * 256 and blocks[-1].height == 300 - 256


def test_screen_to_ground_inverts_the_projection(bounds, render_config):
    projection = IsoProjection.create(bounds, render_config)
    px, py = projection.world_to_native(37.0, 81.0)
    x, y = screen_to_ground(projection, px, py)
    assert abs(x - 37.0) < 1e-6 and abs(y - 81.0) < 1e-6


def test_block_render_matches_whole_render(tmp_path, bounds, render_config, scene):  # noqa: F811
    whole = composite(
        render_layers(bounds, render_config, scene),
        parse_color(render_config.palette["background"]),
    )
    info = render_blocks(bounds, render_config, scene, tmp_path, block_px=256)
    assert len(info["blocks"]) > 2
    assembled = read_region(tmp_path, "render", (0, 0, info["width"], info["height"]), "RGB")
    assert np.array_equal(np.asarray(whole), np.asarray(assembled))


def test_ground_window_reaches_tall_buildings_below_the_block(bounds, render_config):
    projection = IsoProjection.create(bounds, render_config)
    block = block_grid(projection.native_width, projection.native_height, 256)[0]
    window = ground_window(projection, block, render_config)
    corner = screen_to_ground(projection, block.left + 10, block.top + block.height + 100)
    from shapely.geometry import Point

    assert window.contains(Point(corner))


def test_block_pyramid_matches_whole_image_pyramid(tmp_path):
    rng = np.random.default_rng(3)
    pixels = rng.integers(0, 4, size=(300, 700)).astype(np.uint8) * 60
    master = Image.fromarray(np.dstack([pixels, pixels // 2, 255 - pixels]), "RGB")
    tiles = TileConfig(tile_size=128, overlap=1, format="png", lossless=True)
    whole_levels = write_pyramid(master, tmp_path / "whole", tiles)
    blocks = [
        (
            (left, top),
            (lambda x0=left, y0=top: master.crop((x0, y0, min(x0 + 256, 700), min(y0 + 256, 300)))),
        )
        for top in (0, 256)
        for left in (0, 256, 512)
    ]
    block_levels = write_pyramid_blocks(
        blocks, 700, 300, "RGB", tmp_path / "blocks", tiles, tmp_path / "work"
    )
    assert block_levels == whole_levels
    for entry in whole_levels:
        for path in sorted((tmp_path / "whole" / str(entry["level"])).iterdir()):
            other = tmp_path / "blocks" / str(entry["level"]) / path.name
            with Image.open(path) as a, Image.open(other) as b:
                assert a.tobytes() == b.tobytes(), path.name
    assert not (tmp_path / "work").exists()


def test_render_resumes_finished_blocks_with_the_same_inputs(
    tmp_path,
    bounds,
    render_config,
    scene,  # noqa: F811
):
    render_blocks(bounds, render_config, scene, tmp_path, block_px=256, inputs_key="a")
    marker = tmp_path / "render_0_0.png"
    stamp = marker.stat().st_mtime_ns
    (tmp_path / "render_1_0.png").unlink()
    render_blocks(bounds, render_config, scene, tmp_path, block_px=256, inputs_key="a")
    assert marker.stat().st_mtime_ns == stamp
    assert (tmp_path / "render_1_0.png").exists()
    render_blocks(bounds, render_config, scene, tmp_path, block_px=256, inputs_key="b")
    assert marker.stat().st_mtime_ns != stamp
