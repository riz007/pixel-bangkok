import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import box

from pixel_bangkok.rasters import (
    NODATA,
    AreaGrid,
    canopy_quadkeys,
    footprint_values,
    open_buildings_band_indexes,
    open_buildings_sources,
    quadkey,
    read_layer,
    resample_onto_grid,
    sample_point,
    write_layer,
)


def test_quadkey_matches_the_canopy_tile_for_wat_arun():
    assert quadkey(100.4897, 13.7437, 9) == "132203310"


def test_small_area_needs_one_canopy_tile(bounds):
    assert canopy_quadkeys(bounds) == ["132203310"]


def test_grid_is_anchored_at_the_area_north_west_corner(bounds):
    grid = AreaGrid.for_bounds(bounds, 0.5)
    assert (grid.width, grid.height) == (400, 200)
    left, bottom, right, top = grid.projected_bounds
    assert left == pytest.approx(bounds.origin_easting)
    assert bottom == pytest.approx(bounds.origin_northing)
    assert right - left == pytest.approx(bounds.width_m)
    assert top - bottom == pytest.approx(bounds.height_m)


MANIFEST = {
    "uriPrefix": "gs://bucket/v1/geotiffs/3",
    "bands": [
        {"id": "building_fractional_count"},
        {"id": "building_height", "tilesetBandIndex": 1},
        {"id": "building_presence", "tilesetBandIndex": 2},
    ],
    "tilesets": [
        {
            "sources": [
                {
                    "uris": ["0e2c/tile_a.tif"],
                    "affineTransform": {
                        "scaleX": 0.5,
                        "translateX": 0,
                        "scaleY": -0.5,
                        "translateY": 1000,
                    },
                    "dimensions": {"width": 1000, "height": 1000},
                },
                {
                    "uris": ["0e2c/tile_b.tif"],
                    "affineTransform": {
                        "scaleX": 0.5,
                        "translateX": 500,
                        "scaleY": -0.5,
                        "translateY": 1000,
                    },
                    "dimensions": {"width": 1000, "height": 1000},
                },
            ]
        }
    ],
}


def test_manifest_sources_are_selected_by_extent():
    assert open_buildings_sources(MANIFEST, (100, 600, 200, 700)) == [
        "https://storage.googleapis.com/bucket/v1/geotiffs/30e2c/tile_a.tif"
    ]
    assert len(open_buildings_sources(MANIFEST, (450, 600, 550, 700))) == 2
    assert open_buildings_sources(MANIFEST, (2000, 0, 2100, 100)) == []


def test_manifest_band_indexes_are_one_based():
    assert open_buildings_band_indexes(MANIFEST) == {
        "building_fractional_count": 1,
        "building_height": 2,
        "building_presence": 3,
    }


def test_resampling_reprojects_a_geographic_source_onto_the_grid(tmp_path, bounds):
    south, west, north, east = bounds.geographic_bbox(buffer_m=50)
    resolution = 0.00001
    width = int((east - west) / resolution) + 1
    height = int((north - south) / resolution) + 1
    data = np.full((height, width), 3, dtype=np.uint8)
    data[:, : width // 2] = 7
    source_path = tmp_path / "source.tif"
    with rasterio.open(
        source_path,
        "w",
        driver="GTiff",
        width=width,
        height=height,
        count=1,
        dtype="uint8",
        crs="EPSG:4326",
        transform=from_origin(west, north, resolution, resolution),
    ) as output:
        output.write(data, 1)

    grid = AreaGrid.for_bounds(bounds, 1.0)
    resampled = resample_onto_grid([str(source_path)], [1], grid, None)
    assert resampled.shape == (1, grid.height, grid.width)
    assert not (resampled == NODATA).any()

    out = tmp_path / "canopy.tif"
    write_layer(out, resampled, grid, ["canopy_height"])
    layer = read_layer(out)
    assert layer.band_names == ("canopy_height",)
    west_lon, _ = bounds.world_to_lonlat(5, 50)
    centre_lon = (west + east) / 2
    assert west_lon < centre_lon
    assert sample_point(layer, "canopy_height", 5, 50, bounds) == 7
    assert sample_point(layer, "canopy_height", 195, 50, bounds) == 3
    assert sample_point(layer, "canopy_height", -5, 50, bounds) == NODATA
    values = footprint_values(layer, "canopy_height", box(190, 40, 195, 45), bounds)
    assert values.size == 25 and set(values.tolist()) == {3.0}
