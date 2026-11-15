from __future__ import annotations

import pytest

from pixel_bangkok.config import AreaConfig, RenderConfig, load_render_config, parse_area_config
from pixel_bangkok.crs import MapBounds

AREA = {
    "id": "test-area",
    "name": {"en": "Synthetic test area"},
    "crs": "EPSG:32647",
    "center": {"lon": 100.4897, "lat": 13.7437},
    "width_m": 200,
    "height_m": 100,
    "source": {
        "provider": "Synthetic",
        "dataset": "Synthetic fixture",
        "licence": "n/a",
        "attribution": "synthetic",
        "attribution_url": "https://example.invalid",
        "overpass_endpoints": ["https://example.invalid/api"],
    },
}


@pytest.fixture
def area() -> AreaConfig:
    return parse_area_config(AREA)


@pytest.fixture
def bounds(area: AreaConfig) -> MapBounds:
    return MapBounds.from_area(area)


@pytest.fixture
def render_config() -> RenderConfig:
    return load_render_config()


def _nodes(bounds: MapBounds, coords: list[tuple[float, float]]) -> list[dict[str, float]]:
    return [
        {"lon": lon, "lat": lat} for lon, lat in (bounds.world_to_lonlat(x, y) for x, y in coords)
    ]


def _square(x: float, y: float, size: float) -> list[tuple[float, float]]:
    return [(x, y), (x + size, y), (x + size, y + size), (x, y + size), (x, y)]


@pytest.fixture
def raw_osm(bounds: MapBounds) -> dict:
    """Synthetic Overpass-shaped scene, positions given in world metres."""

    def way(way_id: int, coords: list[tuple[float, float]], tags: dict[str, str]) -> dict:
        return {"type": "way", "id": way_id, "tags": tags, "geometry": _nodes(bounds, coords)}

    lon, lat = bounds.world_to_lonlat(150, 20)
    return {
        "elements": [
            way(1, _square(40, 40, 20), {"building": "yes", "height": "12"}),
            way(2, _square(90, 40, 10), {"building": "temple", "building:levels": "2"}),
            way(3, _square(120, 60, 10), {"building": "yes", "man_made": "tower"}),
            way(4, _square(120, 60, 10), {"building": "yes"}),
            way(5, _square(190, 80, 30), {"building": "yes"}),
            way(6, _square(400, 400, 10), {"building": "yes"}),
            way(7, _square(92, 42, 4), {"building:part": "yes"}),
            way(
                8,
                [(20, 20), (30, 20), (30, 30), (20, 20), (30, 30), (20, 30), (20, 20)],
                {"building": "yes"},
            ),
            way(10, [(-50, 10), (250, 10)], {"highway": "residential", "name": "Test Road"}),
            way(11, [(0, 30), (100, 30)], {"highway": "footway", "width": "3"}),
            way(20, _square(0, 70, 30), {"natural": "water", "water": "pond"}),
            way(21, [(0, 90), (200, 90)], {"waterway": "canal"}),
            way(22, [(0, 95), (200, 95)], {"waterway": "river"}),
            way(30, _square(150, 30, 20), {"leisure": "park"}),
            {"type": "node", "id": 40, "lon": lon, "lat": lat, "tags": {"natural": "tree"}},
            {"type": "node", "id": 41, "lon": lon, "lat": lat, "tags": {"amenity": "bench"}},
        ]
    }
