import numpy as np

from pixel_bangkok.pixelart import edge_dissolve
from pixel_bangkok.projection import IsoProjection


def test_fade_is_solid_outside_clear_inside_and_dithered_between(bounds, render_config):
    projection = IsoProjection.create(bounds, render_config)
    box = (0, 0, projection.native_width, projection.native_height)
    dissolve = edge_dissolve(bounds, render_config, box)
    cx, cy = projection.world_to_native(bounds.width_m / 2, bounds.height_m / 2)
    assert not dissolve[int(cy), int(cx)]
    assert dissolve[0, 0] and dissolve[-1, -1]
    columns = []
    for y in np.linspace(0, bounds.height_m / 2, 60):
        px, py = projection.world_to_native(bounds.width_m / 2, float(y))
        columns.append(dissolve[int(py), int(px)])
    assert columns[0] and not columns[-1]
    assert 0 < np.mean(columns) < 1


def test_fade_matches_across_blocks(bounds, render_config):
    projection = IsoProjection.create(bounds, render_config)
    width, height = projection.native_width, projection.native_height
    whole = edge_dissolve(bounds, render_config, (0, 0, width, height))
    left = edge_dissolve(bounds, render_config, (0, 0, width // 2, height))
    right = edge_dissolve(bounds, render_config, (width // 2, 0, width, height))
    assert np.array_equal(whole, np.hstack([left, right]))


def test_fade_is_complete_at_the_area_edge(bounds, render_config):
    projection = IsoProjection.create(bounds, render_config)
    box = (0, 0, projection.native_width, projection.native_height)
    dissolve = edge_dissolve(bounds, render_config, box)
    for x in np.linspace(1, bounds.width_m - 1, 25):
        px, py = projection.world_to_native(float(x), 0.2)
        assert dissolve[int(py), int(px)]
