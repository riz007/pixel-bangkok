from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class SourceConfig:
    provider: str
    dataset: str
    licence: str
    attribution: str
    attribution_url: str
    overpass_endpoints: tuple[str, ...]


@dataclass(frozen=True)
class AreaConfig:
    id: str
    name_en: str
    name_th: str | None
    crs: str
    center_lon: float
    center_lat: float
    width_m: float
    height_m: float
    source: SourceConfig


@dataclass(frozen=True)
class TileConfig:
    tile_size: int
    overlap: int
    format: str
    lossless: bool


@dataclass(frozen=True)
class RenderConfig:
    camera_azimuth_deg: float
    camera_elevation_deg: float
    pixels_per_metre: int
    upscale: int
    max_height_m: float
    light_azimuth_deg: float
    shadow_length_per_metre: float
    floor_height_m: float
    unknown_height_m: float
    road_widths_m: dict[str, float]
    waterway_widths_m: dict[str, float]
    tree_height_m: float
    tree_canopy_radius_m: float
    palette: dict[str, str]
    tiles: TileConfig


@dataclass(frozen=True)
class Paths:
    raw_dir: Path
    processed_dir: Path
    build_dir: Path
    curated_dir: Path
    publish_dir: Path

    @classmethod
    def for_area(cls, area_id: str, root: Path = REPO_ROOT) -> Paths:
        return cls(
            raw_dir=root / "data" / "raw" / area_id,
            processed_dir=root / "data" / "processed" / area_id,
            build_dir=root / "build" / area_id,
            curated_dir=root / "data" / "curated" / area_id,
            publish_dir=root / "apps" / "web" / "public" / "maps" / area_id,
        )


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"config file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"{path} must contain a JSON object")
    return data


def _require(data: dict[str, Any], key: str, context: str) -> Any:
    if key not in data:
        raise ConfigError(f"missing '{key}' in {context}")
    return data[key]


def parse_area_config(data: dict[str, Any]) -> AreaConfig:
    center = _require(data, "center", "area config")
    name = _require(data, "name", "area config")
    source = _require(data, "source", "area config")
    width_m = float(_require(data, "width_m", "area config"))
    height_m = float(_require(data, "height_m", "area config"))
    if width_m <= 0 or height_m <= 0:
        raise ConfigError("area width_m and height_m must be positive")
    lon = float(_require(center, "lon", "area center"))
    lat = float(_require(center, "lat", "area center"))
    if not (-180 <= lon <= 180 and -90 <= lat <= 90):
        raise ConfigError("area center must be longitude/latitude in degrees")
    endpoints = tuple(_require(source, "overpass_endpoints", "area source"))
    if not endpoints:
        raise ConfigError("at least one Overpass endpoint is required")
    return AreaConfig(
        id=str(_require(data, "id", "area config")),
        name_en=str(_require(name, "en", "area name")),
        name_th=name.get("th"),
        crs=str(_require(data, "crs", "area config")),
        center_lon=lon,
        center_lat=lat,
        width_m=width_m,
        height_m=height_m,
        source=SourceConfig(
            provider=str(_require(source, "provider", "area source")),
            dataset=str(_require(source, "dataset", "area source")),
            licence=str(_require(source, "licence", "area source")),
            attribution=str(_require(source, "attribution", "area source")),
            attribution_url=str(_require(source, "attribution_url", "area source")),
            overpass_endpoints=endpoints,
        ),
    )


def parse_render_config(data: dict[str, Any]) -> RenderConfig:
    camera = _require(data, "camera", "render config")
    light = _require(data, "light", "render config")
    heights = _require(data, "heights", "render config")
    tiles = _require(data, "tiles", "render config")
    tree = _require(data, "tree_symbol", "render config")
    ppm = _require(data, "pixels_per_metre", "render config")
    upscale = _require(data, "upscale", "render config")
    if not isinstance(ppm, int) or not isinstance(upscale, int) or ppm < 1 or upscale < 1:
        raise ConfigError("pixels_per_metre and upscale must be positive integers")
    elevation = float(_require(camera, "elevation_deg", "camera"))
    if not 0 < elevation < 90:
        raise ConfigError("camera elevation_deg must be between 0 and 90 (exclusive)")
    tile_format = str(_require(tiles, "format", "tiles"))
    if tile_format not in {"webp", "png"}:
        raise ConfigError("tiles.format must be 'webp' or 'png'")
    tile_size = int(_require(tiles, "tile_size", "tiles"))
    overlap = int(_require(tiles, "overlap", "tiles"))
    if tile_size < 1 or overlap < 0:
        raise ConfigError("tile_size must be positive and overlap non-negative")
    return RenderConfig(
        camera_azimuth_deg=float(_require(camera, "azimuth_deg", "camera")),
        camera_elevation_deg=elevation,
        pixels_per_metre=ppm,
        upscale=upscale,
        max_height_m=float(_require(data, "max_height_m", "render config")),
        light_azimuth_deg=float(_require(light, "azimuth_deg", "light")),
        shadow_length_per_metre=float(_require(light, "shadow_length_per_metre", "light")),
        floor_height_m=float(_require(heights, "floor_height_m", "heights")),
        unknown_height_m=float(_require(heights, "unknown_height_m", "heights")),
        road_widths_m=dict(_require(data, "road_widths_m", "render config")),
        waterway_widths_m=dict(_require(data, "waterway_widths_m", "render config")),
        tree_height_m=float(_require(tree, "height_m", "tree_symbol")),
        tree_canopy_radius_m=float(_require(tree, "canopy_radius_m", "tree_symbol")),
        palette=dict(_require(data, "palette", "render config")),
        tiles=TileConfig(
            tile_size=tile_size,
            overlap=overlap,
            format=tile_format,
            lossless=bool(tiles.get("lossless", True)),
        ),
    )


def load_area_config(area_id: str, root: Path = REPO_ROOT) -> AreaConfig:
    return parse_area_config(_read_json(root / "config" / "areas" / f"{area_id}.json"))


def load_render_config(root: Path = REPO_ROOT) -> RenderConfig:
    return parse_render_config(_read_json(root / "config" / "render.json"))
