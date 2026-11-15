import dataclasses
import math

import pytest

from pixel_bangkok.projection import IsoProjection


@pytest.fixture
def projection(bounds, render_config):
    return IsoProjection.create(bounds, render_config)


def test_all_corners_fit_inside_canvas(projection, bounds, render_config):
    for x in (0, bounds.width_m):
        for y in (0, bounds.height_m):
            for z in (0, render_config.max_height_m):
                px, py = projection.world_to_native(x, y, z)
                assert 0 <= px <= projection.native_width - 1
                assert 0 <= py <= projection.native_height - 1


def test_height_moves_straight_up(projection, render_config):
    ground = projection.world_to_native(50, 50, 0)
    raised = projection.world_to_native(50, 50, 10)
    expected = 10 * math.cos(math.radians(render_config.camera_elevation_deg))
    assert raised[0] == pytest.approx(ground[0])
    assert ground[1] - raised[1] == pytest.approx(expected * render_config.pixels_per_metre)


def test_azimuth_bearing_points_up_the_screen(bounds, render_config):
    north_up = IsoProjection.create(
        bounds, dataclasses.replace(render_config, camera_azimuth_deg=0)
    )
    origin = north_up.world_to_native(10, 10)
    north = north_up.world_to_native(10, 20)
    east = north_up.world_to_native(20, 10)
    assert north[0] == pytest.approx(origin[0]) and north[1] < origin[1]
    assert east[1] == pytest.approx(origin[1]) and east[0] > origin[0]

    northwest_up = IsoProjection.create(
        bounds, dataclasses.replace(render_config, camera_azimuth_deg=315)
    )
    origin = northwest_up.world_to_native(10, 10)
    north = northwest_up.world_to_native(10, 20)
    assert north[0] > origin[0] and north[1] < origin[1]


def test_depth_increases_away_from_camera(projection):
    near = projection.world_to_native(100, 0)
    far = projection.world_to_native(0, 100)
    assert far[1] < near[1]
    assert projection.depth(0, 100) > projection.depth(100, 0)


def test_master_is_native_times_upscale_and_matches_matrix(projection):
    x, y, z = 33.0, 71.0, 12.0
    native = projection.world_to_native(x, y, z)
    master = projection.world_to_master(x, y, z)
    assert master == pytest.approx((native[0] * projection.upscale, native[1] * projection.upscale))
    matrix = projection.master_matrix()
    px = matrix["px"][0] * x + matrix["px"][1] * y + matrix["px"][2] * z + matrix["px"][3]
    py = matrix["py"][0] * x + matrix["py"][1] * y + matrix["py"][2] * z + matrix["py"][3]
    assert (px, py) == pytest.approx(master)
    assert projection.master_width == projection.native_width * projection.upscale
