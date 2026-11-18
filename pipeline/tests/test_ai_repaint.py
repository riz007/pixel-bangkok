import json

import numpy as np
from PIL import Image

from pixel_bangkok import ai_repaint
from pixel_bangkok.ai_repaint import compose, feather, snap_palette, window_positions
from pixel_bangkok.blocks import block_grid


def test_windows_cover_the_image_with_overlap():
    positions = window_positions(3000, 1500)
    lefts = sorted({left for left, _ in positions})
    tops = sorted({top for _, top in positions})
    assert lefts[0] == 0 and lefts[-1] == 3000 - 1024
    assert tops[0] == 0 and tops[-1] == 1500 - 1024
    assert all(b - a <= 768 for a, b in zip(lefts, lefts[1:], strict=False))
    assert window_positions(500, 400) == [(0, 0)]


def test_feather_ramps_only_where_neighbours_exist():
    inner = feather(1024, 256, False, False)
    assert inner[0] < 0.01 and inner[-1] < 0.01 and inner[512] == 1
    edge = feather(1024, 256, True, False)
    assert edge[0] == 1 and edge[-1] < 0.01
    overlap = inner[768:1024] + inner[:256]
    assert np.allclose(overlap, 1.0, atol=0.01)


def test_snap_palette_limits_colours():
    rng = np.random.default_rng(1)
    image = Image.fromarray(rng.integers(0, 256, (64, 64, 3), dtype=np.uint8), "RGB")
    assert len(set(snap_palette(image, 16).get_flattened_data())) <= 16


def test_compose_blends_accepted_windows_and_keeps_procedural_elsewhere(tmp_path, render_config):
    build = tmp_path
    blocks_dir = build / "blocks"
    blocks_dir.mkdir()
    width, height = 1500, 1100
    blocks = block_grid(width, height, 1024)
    for block in blocks:
        Image.new("RGB", (block.width, block.height), (10, 20, 30)).save(
            blocks_dir / f"master_{block.name}.png"
        )
        mask = np.zeros((block.height, block.width), dtype=bool)
        mask[:10, :10] = True
        Image.fromarray(mask).save(blocks_dir / f"occlusion_{block.name}.png")
    (blocks_dir / "blocks.json").write_text(
        json.dumps(
            {
                "width": width,
                "height": height,
                "block_px": 1024,
                "blocks": [block.__dict__ for block in blocks],
            }
        )
    )
    ai_dir = build / "ai"
    (ai_dir / "windows").mkdir(parents=True)
    Image.new("RGB", (1024, 1024), (200, 100, 50)).save(ai_dir / "windows" / "0_0.png")
    (ai_dir / "state.json").write_text(
        json.dumps(
            {
                "windows": {
                    "0_0": {"left": 0, "top": 0, "accepted": True},
                    "476_0": {"left": 476, "top": 0, "accepted": False},
                }
            }
        )
    )
    summary = compose(render_config, build)
    assert summary["windows_accepted"] == 1 and summary["windows_rejected"] == 1
    with Image.open(blocks_dir / "ai_master_0_0.png") as image:
        assert image.getpixel((5, 5)) == (200, 100, 50)
        assert image.getpixel((1020, 1020)) == (10, 20, 30) or image.getpixel((1020, 1020)) != (
            200,
            100,
            50,
        )
    with Image.open(blocks_dir / "ai_master_1_1.png") as image:
        assert image.getpixel((300, 50)) == (10, 20, 30)
    with Image.open(blocks_dir / "ai_overlay_0_0.png") as image:
        assert image.getpixel((5, 5))[3] == 255
        assert image.getpixel((50, 50))[3] == 0
    assert 0 < summary["coverage"] < 1
    assert ai_repaint.LICENCE.startswith("Qwen Research License")


def test_new_windows_are_conditioned_on_finished_neighbours(tmp_path):
    from pixel_bangkok.ai_repaint import condition_on_neighbours

    ai_dir = tmp_path / "ai"
    (ai_dir / "windows").mkdir(parents=True)
    Image.new("RGB", (1024, 1024), (200, 100, 50)).save(ai_dir / "windows" / "0_0.png")
    state = {"windows": {"0_0": {"left": 0, "top": 0, "accepted": True}}}
    procedural = Image.new("RGB", (1024, 1024), (10, 20, 30))
    image_size = (3000, 1024)

    neighbour = {"id": "768_0", "left": 768, "top": 0}
    conditioned, mask = condition_on_neighbours(ai_dir, state, neighbour, procedural, image_size)
    near = conditioned.getpixel((10, 500))
    assert all(abs(a - b) <= 10 for a, b in zip(near, (200, 100, 50), strict=True))
    assert mask.getpixel((10, 500)) == 0
    assert mask.getpixel((200, 500)) == 255
    assert conditioned.getpixel((600, 500)) == (10, 20, 30)
    assert mask.getpixel((600, 500)) == 255

    far = {"id": "1976_0", "left": 1976, "top": 0}
    assert condition_on_neighbours(ai_dir, state, far, procedural, image_size) is None
    assert (
        condition_on_neighbours(
            ai_dir, state, {"id": "0_0", "left": 0, "top": 0}, procedural, image_size
        )
        is None
    )


def test_windows_whose_render_changed_are_queued_again(tmp_path):
    blocks_dir = tmp_path / "blocks"
    blocks_dir.mkdir()
    blocks = block_grid(2048, 1024, 1024)
    for block in blocks:
        Image.new("RGB", (block.width, block.height), (10, 20, 30)).save(
            blocks_dir / f"master_{block.name}.png"
        )
    (blocks_dir / "blocks.json").write_text(
        json.dumps(
            {
                "width": 2048,
                "height": 1024,
                "block_px": 1024,
                "blocks": [block.__dict__ for block in blocks],
            }
        )
    )
    windows = tmp_path / "ai" / "windows"
    windows.mkdir(parents=True)
    Image.new("RGB", (1024, 1024), (10, 20, 30)).save(windows / "0_0.in.png")
    changed = Image.new("RGB", (1024, 1024), (10, 20, 30))
    changed.paste((99, 99, 99), (500, 500, 510, 510))
    changed.save(windows / "1024_0.in.png")
    nearly = Image.open(windows / "0_0.in.png").copy()
    nearly.putpixel((3, 3), (0, 0, 0))
    nearly.save(windows / "0_0.in.png")
    for name in ("0_0", "1024_0"):
        Image.new("RGB", (1024, 1024), (1, 2, 3)).save(windows / f"{name}.png")
    (tmp_path / "ai" / "state.json").write_text(
        json.dumps(
            {
                "windows": {
                    "0_0": {"left": 0, "top": 0, "accepted": True},
                    "1024_0": {"left": 1024, "top": 0, "accepted": True},
                }
            }
        )
    )
    assert ai_repaint.invalidate(tmp_path) == ["1024_0"]
    state = json.loads((tmp_path / "ai" / "state.json").read_text())
    assert list(state["windows"]) == ["0_0"]
    assert (windows / "stale" / "1024_0.png").exists()
    assert not (windows / "1024_0.png").exists()
    assert ai_repaint.invalidate(tmp_path) == []
