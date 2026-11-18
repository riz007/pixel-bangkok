import pytest

from pixel_bangkok.crs import MapBounds


def test_center_maps_to_middle_of_world(area, bounds):
    x, y = bounds.lonlat_to_world(area.center_lon, area.center_lat)
    assert x == pytest.approx(100, abs=0.001)
    assert y == pytest.approx(50, abs=0.001)


def test_known_utm_47n_control_point(bounds):
    # 100.4897 E, 13.7437 N in EPSG:32647, independently computed with pyproj/PROJ.
    assert bounds.origin_easting + 100 == pytest.approx(661066.762, abs=0.01)
    assert bounds.origin_northing + 50 == pytest.approx(1519878.641, abs=0.01)


def test_axis_order_is_longitude_then_latitude(bounds, area):
    x_east, y_east = bounds.lonlat_to_world(area.center_lon + 0.001, area.center_lat)
    x_north, y_north = bounds.lonlat_to_world(area.center_lon, area.center_lat + 0.001)
    assert x_east - 100 == pytest.approx(108.2, abs=0.5)
    assert abs(y_east - 50) < 1
    assert y_north - 50 == pytest.approx(110.6, abs=0.5)
    assert abs(x_north - 100) < 1


def test_round_trip(bounds):
    lon, lat = bounds.world_to_lonlat(37.5, 81.25)
    x, y = bounds.lonlat_to_world(lon, lat)
    assert (x, y) == pytest.approx((37.5, 81.25), abs=1e-4)


def test_geographic_bbox_encloses_corners(bounds: MapBounds):
    south, west, north, east = bounds.geographic_bbox()
    for x in (0, bounds.width_m):
        for y in (0, bounds.height_m):
            lon, lat = bounds.world_to_lonlat(x, y)
            assert west <= lon <= east
            assert south <= lat <= north
    assert bounds.contains_world(0, 0)
    assert not bounds.contains_world(-0.1, 0)


def test_browser_transforms_match_pyproj(bounds):
    transforms = bounds.browser_transforms()
    forward = transforms["lonlat_to_world"]
    inverse = transforms["world_to_lonlat"]
    assert forward["max_error_m"] < 0.05 and inverse["max_error_m"] < 0.05
    x, y = 37.0, 81.0
    lon, lat = bounds.world_to_lonlat(x, y)

    def evaluate(fit, keys, u, v):
        terms = [1, u, v, u * u, u * v, v * v]
        return [sum(c * t for c, t in zip(fit[key], terms, strict=True)) for key in keys]

    fx, fy = evaluate(forward, ("x", "y"), lon - forward["origin"][0], lat - forward["origin"][1])
    assert abs(fx - x) < 0.05 and abs(fy - y) < 0.05
    flon, flat = evaluate(
        inverse, ("lon", "lat"), x - inverse["origin"][0], y - inverse["origin"][1]
    )
    assert abs(flon - lon) < 1e-6 and abs(flat - lat) < 1e-6
