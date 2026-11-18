import numpy as np
from shapely.geometry import box

from pixel_bangkok.rasters import AreaGrid, RasterLayer
from pixel_bangkok.trees import crown_radius, place_canopy_trees


def _canopy(bounds, tall_columns):
    grid = AreaGrid.for_bounds(bounds, 1.0)
    data = np.zeros((1, grid.height, grid.width), dtype=np.float32)
    data[0, :, :tall_columns] = 8.0
    return RasterLayer(data, grid.transform, grid.crs, ("canopy_height",))


def test_trees_only_where_canopy_is_tall_and_ground_is_free(bounds, render_config):
    canopy = _canopy(bounds, 100)
    blocked = box(0, 0, 40, 100)
    trees = place_canopy_trees(canopy, bounds, blocked, render_config.trees, seed=1)
    assert trees
    for point, height in trees:
        assert 40 <= point.x < 100
        assert height == 8.0


def test_tree_placement_is_deterministic(bounds, render_config):
    canopy = _canopy(bounds, 200)
    first = place_canopy_trees(canopy, bounds, box(0, 0, 0, 0), render_config.trees, seed=7)
    second = place_canopy_trees(canopy, bounds, box(0, 0, 0, 0), render_config.trees, seed=7)
    other = place_canopy_trees(canopy, bounds, box(0, 0, 0, 0), render_config.trees, seed=8)
    assert [p.wkt for p, _ in first] == [p.wkt for p, _ in second]
    assert [p.wkt for p, _ in first] != [p.wkt for p, _ in other]


def test_crown_radius_is_clamped(render_config):
    config = render_config.trees
    assert crown_radius(1.0, config) == config.min_crown_radius_m
    assert crown_radius(100.0, config) == config.max_crown_radius_m
    assert crown_radius(8.0, config) == round(8.0 * config.crown_radius_per_metre, 2)


def test_compact_tree_file_round_trips(tmp_path):
    from pixel_bangkok.trees import read_compact, write_compact

    path = tmp_path / "trees.render.npz"
    write_compact(path, [(1.5, 2.5, 8.0, 3.0, "canopy/0"), (10.0, 20.0, 6.0, 2.5, "node/7")])
    trees = read_compact(path)
    assert [(p.x, p.y) for p, _ in trees] == [(1.5, 2.5), (10.0, 20.0)]
    assert trees[1][1] == {"source_id": "node/7", "height_m": 6.0, "crown_radius_m": 2.5}
    write_compact(path, [])
    assert read_compact(path) == []
