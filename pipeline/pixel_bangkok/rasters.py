"""Raster sources: fetch windows onto the area grid, then read and sample them.

Every fetched raster is written as a GeoTIFF in the area's projected CRS
(EPSG:32647 for Bangkok), with its origin at the area's north-west corner and
square pixels of the configured resolution. Rows run north to south.

Sources:
- Google Open Buildings 2.5D Temporal: bands `building_height` (metres above
  ground, capped at 100) and `building_presence` (0-1). Public GCS bucket.
- Meta/WRI High Resolution Canopy Height: one band, canopy height in metres.
  Public S3 bucket, EPSG:3857 tiles named by zoom-9 quadkey.
"""

from __future__ import annotations

import json
import logging
import math
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
import rasterio.errors
from rasterio.enums import Resampling
from rasterio.features import geometry_mask
from rasterio.transform import Affine, from_origin
from rasterio.warp import reproject, transform_bounds
from rasterio.windows import Window, from_bounds
from shapely.affinity import translate
from shapely.geometry import mapping
from shapely.geometry.base import BaseGeometry

from .config import RasterSourceConfig
from .crs import MapBounds

log = logging.getLogger(__name__)

NODATA = -99.0
OPEN_BUILDINGS_BUCKET = "open-buildings-temporal-data"
OPEN_BUILDINGS_LIST_URL = f"https://storage.googleapis.com/storage/v1/b/{OPEN_BUILDINGS_BUCKET}/o"
CANOPY_BASE_URL = (
    "https://dataforgood-fb-data.s3.amazonaws.com/forests/v1/alsgedi_global_v6_float/chm"
)
CANOPY_QUADKEY_ZOOM = 9
WINDOW_MARGIN_M = 10.0
GDAL_ENV = {
    "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
    "GDAL_HTTP_MAX_RETRY": "4",
    "GDAL_HTTP_RETRY_DELAY": "2",
    "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif",
}


@dataclass(frozen=True)
class AreaGrid:
    crs: str
    transform: Affine
    width: int
    height: int

    @classmethod
    def for_bounds(cls, bounds: MapBounds, resolution_m: float) -> AreaGrid:
        return cls(
            crs=bounds.crs,
            transform=from_origin(
                bounds.origin_easting,
                bounds.origin_northing + bounds.height_m,
                resolution_m,
                resolution_m,
            ),
            width=math.ceil(bounds.width_m / resolution_m),
            height=math.ceil(bounds.height_m / resolution_m),
        )

    @property
    def projected_bounds(self) -> tuple[float, float, float, float]:
        left, top = self.transform.c, self.transform.f
        return (
            left,
            top + self.transform.e * self.height,
            left + self.transform.a * self.width,
            top,
        )


@dataclass(frozen=True)
class RasterLayer:
    data: np.ndarray
    transform: Affine
    crs: str
    band_names: tuple[str, ...]

    def band(self, name: str) -> np.ndarray:
        return self.data[self.band_names.index(name)]


def _https(uri: str) -> str:
    if uri.startswith("gs://"):
        return "https://storage.googleapis.com/" + uri.removeprefix("gs://")
    return uri


def _get_json(url: str, timeout_s: float = 60.0) -> Any:
    with urllib.request.urlopen(url, timeout=timeout_s) as response:
        return json.loads(response.read().decode("utf-8"))


def quadkey(lon: float, lat: float, zoom: int) -> str:
    x, y = _tile_xy(lon, lat, zoom)
    return _tile_quadkey(x, y, zoom)


def _tile_xy(lon: float, lat: float, zoom: int) -> tuple[int, int]:
    n = 2**zoom
    x = int((lon + 180.0) / 360.0 * n)
    y = int((1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * n)
    return min(max(x, 0), n - 1), min(max(y, 0), n - 1)


def _tile_quadkey(x: int, y: int, zoom: int) -> str:
    return "".join(str(((x >> bit) & 1) + 2 * ((y >> bit) & 1)) for bit in range(zoom - 1, -1, -1))


def canopy_quadkeys(bounds: MapBounds, zoom: int = CANOPY_QUADKEY_ZOOM) -> list[str]:
    south, west, north, east = bounds.geographic_bbox(buffer_m=WINDOW_MARGIN_M)
    x0, y0 = _tile_xy(west, north, zoom)
    x1, y1 = _tile_xy(east, south, zoom)
    return [_tile_quadkey(x, y, zoom) for y in range(y0, y1 + 1) for x in range(x0, x1 + 1)]


def open_buildings_sources(
    manifest: dict[str, Any], bounds: tuple[float, float, float, float]
) -> list[str]:
    """HTTPS URLs of manifest GeoTIFFs whose extent intersects (left, bottom, right, top)."""
    left, bottom, right, top = bounds
    prefix = manifest["uriPrefix"].rstrip("/")
    urls = []
    for tileset in manifest["tilesets"]:
        for source in tileset["sources"]:
            affine = source["affineTransform"]
            width = source["dimensions"]["width"] * affine["scaleX"]
            height = source["dimensions"]["height"] * -affine["scaleY"]
            src_left, src_top = affine["translateX"], affine["translateY"]
            if (
                src_left < right
                and src_left + width > left
                and src_top - height < top
                and src_top > bottom
            ):
                urls.extend(_https(f"{prefix}{uri}") for uri in source["uris"])
    return sorted(set(urls))


def open_buildings_band_indexes(manifest: dict[str, Any]) -> dict[str, int]:
    """1-based GeoTIFF band index for each named band in a manifest."""
    return {band["id"]: int(band.get("tilesetBandIndex", 0)) + 1 for band in manifest["bands"]}


def _list_open_buildings_manifests(crs: str, year: int) -> list[str]:
    epsg = crs.replace(":", "_")
    query = urllib.parse.urlencode(
        {
            "prefix": "v1/manifests/",
            "matchGlob": f"v1/manifests/*_{epsg}_{year}_06_30.json",
            "fields": "items(name)",
        }
    )
    listing = _get_json(f"{OPEN_BUILDINGS_LIST_URL}?{query}")
    return sorted(item["name"] for item in listing.get("items", []))


def _cached_manifest(name: str, cache_dir: Path) -> dict[str, Any]:
    path = cache_dir / Path(name).name
    if not path.exists():
        url = f"https://storage.googleapis.com/{OPEN_BUILDINGS_BUCKET}/{name}"
        log.info("downloading Open Buildings manifest %s", url)
        cache_dir.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(url, timeout=120) as response:
            path.write_bytes(response.read())
    return json.loads(path.read_text(encoding="utf-8"))


def resample_onto_grid(
    sources: list[str], bands: list[int], grid: AreaGrid, src_nodata: float | None
) -> np.ndarray:
    """Read only the window each source needs and resample it onto the grid (nearest)."""
    destination = np.full((len(bands), grid.height, grid.width), NODATA, dtype=np.float32)
    with rasterio.Env(**GDAL_ENV):
        for url in sources:
            path = url if Path(url).exists() else f"/vsicurl/{url}"
            with rasterio.open(path) as source:
                left, bottom, right, top = transform_bounds(
                    grid.crs, source.crs, *grid.projected_bounds
                )
                margin = WINDOW_MARGIN_M
                window = (
                    from_bounds(
                        left - margin,
                        bottom - margin,
                        right + margin,
                        top + margin,
                        source.transform,
                    )
                    .round_offsets()
                    .round_lengths()
                )
                try:
                    window = window.intersection(Window(0, 0, source.width, source.height))
                except rasterio.errors.WindowError:
                    continue
                for index, band in enumerate(bands):
                    block = source.read(band, window=window).astype(np.float32)
                    reproject(
                        source=block,
                        destination=destination[index],
                        src_transform=source.window_transform(window),
                        src_crs=source.crs,
                        src_nodata=src_nodata,
                        dst_transform=grid.transform,
                        dst_crs=grid.crs,
                        dst_nodata=NODATA,
                        init_dest_nodata=False,
                        resampling=Resampling.nearest,
                    )
    return destination


def write_layer(path: Path, data: np.ndarray, grid: AreaGrid, band_names: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=grid.width,
        height=grid.height,
        count=data.shape[0],
        dtype="float32",
        crs=grid.crs,
        transform=grid.transform,
        nodata=NODATA,
        compress="deflate",
    ) as output:
        output.write(data)
        for index, name in enumerate(band_names, start=1):
            output.set_band_description(index, name)


def read_layer(path: Path) -> RasterLayer:
    with rasterio.open(path) as source:
        return RasterLayer(
            data=source.read(),
            transform=source.transform,
            crs=str(source.crs),
            band_names=tuple(source.descriptions),
        )


def fetch_building_heights(
    bounds: MapBounds, config: RasterSourceConfig, output: Path, cache_dir: Path
) -> dict[str, Any]:
    if config.year is None:
        raise ValueError("rasters.building_heights.year is required")
    grid = AreaGrid.for_bounds(bounds, config.resolution_m)
    names = _list_open_buildings_manifests(bounds.crs, config.year)
    if not names:
        raise RuntimeError(f"no Open Buildings manifests for {bounds.crs} in {config.year}")
    sources: list[str] = []
    band_indexes: dict[str, int] = {}
    imagery: list[dict[str, Any]] = []
    for name in names:
        manifest = _cached_manifest(name, cache_dir)
        matched = open_buildings_sources(manifest, grid.projected_bounds)
        if matched:
            sources.extend(matched)
            band_indexes = open_buildings_band_indexes(manifest)
            imagery.append({"manifest": name, **manifest.get("properties", {})})
    if not sources:
        raise RuntimeError("no Open Buildings rasters cover this area")
    bands = ["building_height", "building_presence"]
    data = resample_onto_grid(sources, [band_indexes[band] for band in bands], grid, NODATA)
    write_layer(output, data, grid, bands)
    covered = float(np.mean(data[0] != NODATA))
    log.info("building heights: %d source raster(s), %.0f%% coverage", len(sources), covered * 100)
    return {
        "dataset": config.dataset,
        "version": config.version,
        "year": config.year,
        "licence": config.licence,
        "url": config.url,
        "sources": sources,
        "imagery": imagery,
        "coverage": round(covered, 4),
        "retrieved_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }


def fetch_tree_canopy(
    bounds: MapBounds, config: RasterSourceConfig, output: Path
) -> dict[str, Any]:
    grid = AreaGrid.for_bounds(bounds, config.resolution_m)
    sources = [f"{CANOPY_BASE_URL}/{key}.tif" for key in canopy_quadkeys(bounds)]
    data = resample_onto_grid(sources, [1], grid, None)
    write_layer(output, data, grid, ["canopy_height"])
    covered = float(np.mean(data[0] != NODATA))
    log.info("tree canopy: %d source raster(s), %.0f%% coverage", len(sources), covered * 100)
    return {
        "dataset": config.dataset,
        "version": config.version,
        "licence": config.licence,
        "url": config.url,
        "sources": sources,
        "coverage": round(covered, 4),
        "retrieved_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }


def footprint_values(
    layer: RasterLayer, band: str, geometry_world: BaseGeometry, bounds: MapBounds
) -> np.ndarray:
    """Raster values of `band` for pixels whose centres fall inside the footprint."""
    projected = translate(geometry_world, bounds.origin_easting, bounds.origin_northing)
    data = layer.band(band)
    inside = ~geometry_mask(
        [mapping(projected)], out_shape=data.shape, transform=layer.transform, all_touched=False
    )
    return data[inside]


def sample_point(layer: RasterLayer, band: str, x: float, y: float, bounds: MapBounds) -> float:
    column, row = ~layer.transform @ (x + bounds.origin_easting, y + bounds.origin_northing)
    data = layer.band(band)
    row_index, column_index = int(math.floor(row)), int(math.floor(column))
    if not (0 <= row_index < data.shape[0] and 0 <= column_index < data.shape[1]):
        return NODATA
    return float(data[row_index, column_index])
