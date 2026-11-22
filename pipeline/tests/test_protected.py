import json

import numpy as np
import pytest
from PIL import Image
from shapely.geometry import box

from pixel_bangkok import ai_repaint, protected
from pixel_bangkok.projection import IsoProjection


def test_sacred_royal_and_state_buildings_are_protected():
    assert protected.building_is_protected({"category": "temple"})
    assert protected.building_is_protected({"category": "yes", "is_temple": True})
    assert protected.building_is_protected({"category": "yes", "tower_type": "stupa"})
    assert protected.building_is_protected({"category": "mosque"})
    assert protected.building_is_protected({"category": "yes", "roof_shape": "prang"})
    assert not protected.building_is_protected({"category": "house", "roof_shape": "gabled"})


def test_buildings_inside_a_temple_compound_are_protected(bounds):
    compound = box(0, 0, 100, 100)
    hall = box(40, 40, 50, 50)
    shop = box(200, 200, 210, 210)
    layers = {
        "ground": [(compound, {"category": "religious"})],
        "buildings": [
            (hall, {"category": "yes", "render_height_m": 12.0}),
            (shop, {"category": "commercial", "render_height_m": 9.0}),
        ],
    }
    shapes = protected.protected_shapes(layers, [], bounds)
    assert len(shapes) == 2
    assert shapes[1][1] == 12.0 and shapes[1][0].contains(hall)
    assert not any(shape.intersects(shop) for shape, _ in shapes)


def test_mask_covers_the_whole_silhouette_not_only_the_footprint(bounds, render_config):
    projection = IsoProjection.create(bounds, render_config)
    tower = box(100, 100, 110, 110)
    shapes = [(tower, 60.0)]
    cx, cy = projection.world_to_native(105, 105, 0)
    _, top = projection.world_to_native(105, 105, 60)
    area = (int(cx) - 200, int(top) - 50, int(cx) + 200, int(cy) + 50)
    mask = protected.rasterize(shapes, projection, area)
    assert mask[int(cy) - area[1], int(cx) - area[0]] == 1.0
    assert mask[int((cy + top) / 2) - area[1], int(cx) - area[0]] == 1.0
    assert mask[0, 0] == 0.0


def test_compose_keeps_the_drawing_on_protected_places(tmp_path, area, bounds, render_config):
    blocks_dir = tmp_path / "blocks"
    blocks_dir.mkdir()
    projection = IsoProjection.create(bounds, render_config)
    cx, cy = projection.world_to_native(*bounds.lonlat_to_world(area.center_lon, area.center_lat))
    left, top = int(cx) - 512, int(cy) - 512
    width, height = left + 1024, top + 1024
    Image.new("RGB", (width, height), (10, 20, 30)).save(blocks_dir / "master_0_0.png")
    Image.fromarray(np.zeros((height, width), dtype=bool)).save(blocks_dir / "occlusion_0_0.png")
    (blocks_dir / "blocks.json").write_text(
        json.dumps(
            {
                "width": width,
                "height": height,
                "block_px": max(width, height),
                "blocks": [
                    {"column": 0, "row": 0, "left": 0, "top": 0, "width": width, "height": height}
                ],
            }
        )
    )
    ai_dir = tmp_path / "ai"
    (ai_dir / "windows").mkdir(parents=True)
    window = f"{left}_{top}"
    Image.new("RGB", (1024, 1024), (200, 100, 50)).save(ai_dir / "windows" / f"{window}.png")
    (ai_dir / "state.json").write_text(
        json.dumps({"windows": {window: {"left": left, "top": top, "accepted": True}}})
    )
    x, y = bounds.lonlat_to_world(area.center_lon, area.center_lat)
    shapes = [(box(x - 5, y - 5, x + 5, y + 5), 0.0)]
    summary = ai_repaint.compose(render_config, tmp_path, area, shapes)
    assert summary["protected_shapes"] == 1
    with Image.open(blocks_dir / "ai_master_0_0.png") as image:
        assert image.getpixel((int(cx), int(cy))) == (10, 20, 30)
        assert image.getpixel((left + 512 + 60, top + 512)) == (200, 100, 50)


def test_an_ai_folder_never_mixes_engines(tmp_path):
    ai_dir = tmp_path / "ai"
    ai_dir.mkdir()
    (ai_dir / "plan.json").write_text(json.dumps({"windows": []}))
    (ai_dir / "state.json").write_text(
        json.dumps({"windows": {"0_0": {"left": 0, "top": 0, "accepted": True}}})
    )
    (tmp_path / "blocks").mkdir()
    (tmp_path / "blocks" / "blocks.json").write_text(
        json.dumps({"width": 10, "height": 10, "block_px": 10, "blocks": []})
    )
    with pytest.raises(RuntimeError, match="qwen"):
        ai_repaint.run(tmp_path, limit=1, engine_name="mumbai")


def test_mumbai_inputs_get_the_red_border_the_lora_expects():
    framed = np.asarray(ai_repaint.with_border(Image.new("RGB", (16, 16), (1, 2, 3))))
    assert tuple(framed[0, 0]) == (255, 0, 0) and tuple(framed[1, 8]) == (255, 0, 0)
    assert tuple(framed[8, 8]) == (1, 2, 3)


def test_the_judge_ignores_protected_pixels():
    from pixel_bangkok import drift

    rng = np.random.default_rng(1)

    def tiles(height: int, width: int) -> np.ndarray:
        cells = rng.integers(0, 255, (height // 8, width // 8), dtype=np.uint8)
        return np.kron(cells, np.ones((8, 8), dtype=np.uint8))

    texture = tiles(256, 512)
    reference = Image.fromarray(np.dstack([texture] * 3), "RGB")
    noisy = texture.copy()
    noisy[:, 256:] = tiles(256, 256)
    repainted = Image.fromarray(np.dstack([noisy] * 3), "RGB")
    assert not drift.drift(reference, repainted)["passes"]
    ignore = np.zeros((256, 512), dtype=bool)
    ignore[:, 256:] = True
    assert drift.drift(reference, repainted, ignore)["passes"]


def test_protected_pois_protect_nearby_drawn_buildings_only(bounds):
    monument = box(0, 0, 8, 8)
    shop = box(100, 100, 110, 110)
    lon, lat = bounds.world_to_lonlat(4, 4)
    layers = {
        "buildings": [
            (monument, {"category": "yes", "render_height_m": 6.0}),
            (shop, {"category": "commercial", "render_height_m": 9.0}),
        ]
    }
    pois = [{"id": "democracy-monument", "category": "landmark", "lon": lon, "lat": lat}]
    shapes = protected.protected_shapes(layers, pois, bounds)
    assert len(shapes) == 1 and shapes[0][0].contains(monument)
    assert protected.protected_shapes({"buildings": []}, pois, bounds) == []


def test_a_temple_that_loses_its_gilding_or_roofs_is_unrecognisable():
    drawing = np.zeros((64, 64, 3), dtype=np.uint8)
    drawing[:, :] = (235, 230, 215)
    drawing[8:24, 8:56] = (217, 119, 60)  # tiled temple roof
    drawing[30:40, 20:44] = (232, 184, 58)  # gilding
    mask = np.ones((64, 64), dtype=bool)
    same = protected.recognisable(Image.fromarray(drawing), Image.fromarray(drawing), mask)
    assert same["recognisable"]
    greyed = drawing.copy()
    greyed[30:40, 20:44] = (150, 150, 150)
    greyed[8:24, 8:56] = (150, 150, 155)
    result = protected.recognisable(Image.fromarray(drawing), Image.fromarray(greyed), mask)
    assert not result["recognisable"]
    assert {"gold", "temple_roof"} <= set(result["failed"])


def test_places_group_a_compound_with_its_buildings(bounds):
    compound = box(0, 0, 100, 100)
    layers = {
        "ground": [(compound, {"category": "religious", "source_id": "way/9", "name": "Wat"})],
        "buildings": [
            (box(40, 40, 50, 50), {"source_id": "way/1", "render_height_m": 12.0}),
            (box(300, 300, 310, 310), {"source_id": "way/2", "category": "mosque"}),
            (box(500, 500, 510, 510), {"source_id": "way/3", "category": "house"}),
        ],
    }
    places = protected.sensitive_places(layers, [], bounds)
    assert [place.id for place in places] == ["way/9", "way/2"]
    assert len(places[0].shapes) == 2
