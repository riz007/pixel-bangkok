"""Gap-filling buildings from Overture: OSM stays first, nothing lands where it should not."""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
from shapely.geometry import LineString, Polygon, box

from pixel_bangkok import building_fill
from pixel_bangkok.config import AreaConfig, BuildingFillConfig
from pixel_bangkok.crs import MapBounds
from pixel_bangkok.geojson_io import feature

FILL = BuildingFillConfig(
    dataset="Overture Maps buildings",
    release="test",
    path="unused",
    licence="ODbL 1.0",
    attribution="Extra buildings: Overture Maps Foundation",
    url="https://docs.overturemaps.org/attribution/",
)


def _row(bounds: MapBounds, ident: str, world: Polygon, dataset: str, **extra) -> dict:
    geographic = bounds.geometry_to_lonlat(world)
    xmin, ymin, xmax, ymax = geographic.bounds
    return {
        "id": ident,
        "geometry": geographic.wkb,
        "sources": [{"dataset": dataset, "license": "ODbL-1.0"}],
        "height": extra.get("height"),
        "num_floors": extra.get("num_floors"),
        "is_underground": extra.get("is_underground", False),
        "bbox": {"xmin": xmin, "xmax": xmax, "ymin": ymin, "ymax": ymax},
    }


def _write(path: Path, rows: list[dict]) -> Path:
    pq.write_table(pa.Table.from_pylist(rows), path)
    return path


def _layers(bounds: MapBounds) -> dict[str, list[dict]]:
    def item(geometry, **properties):
        return feature(geometry, {"source_id": "test", **properties}, bounds)

    return {
        "buildings": [item(box(10, 10, 30, 30), category="yes")],
        "water": [item(box(100, 10, 160, 40), category="river")],
        "roads": [item(LineString([(10, 70), (90, 70)]), category="residential")],
        "ground": [item(box(150, 55, 195, 95), category="religious")],
    }


def test_fills_gaps_and_keeps_osm_first(tmp_path, area: AreaConfig, bounds: MapBounds):
    area = dataclasses.replace(area, building_fill=FILL)
    rows = [
        _row(bounds, "a-new", box(50, 10, 60, 20), "Google Open Buildings", height=9.0),
        _row(bounds, "b-osm-copy", box(40, 40, 50, 50), "OpenStreetMap"),
        _row(bounds, "c-overlaps-osm", box(12, 12, 28, 28), "Microsoft ML Buildings"),
        _row(bounds, "d-on-water", box(110, 20, 120, 30), "Google Open Buildings"),
        _row(bounds, "e-across-road", box(40, 65, 50, 75), "Google Open Buildings"),
        _row(bounds, "f-in-temple", box(160, 60, 170, 70), "Google Open Buildings"),
        _row(bounds, "g-tiny", box(70, 40, 72, 42), "Google Open Buildings"),
        _row(
            bounds,
            "h-underground",
            box(70, 10, 80, 20),
            "Google Open Buildings",
            is_underground=True,
        ),
    ]
    layers = _layers(bounds)
    stats = building_fill.fill(layers, area, bounds, _write(tmp_path / "b.parquet", rows))

    added = [f["properties"] for f in layers["buildings"][1:]]
    assert [p["source_id"] for p in added] == ["overture/a-new"]
    assert added[0]["source_dataset"] == "Google Open Buildings"
    assert added[0]["source_licence"] == "ODbL-1.0"
    assert added[0]["source_height"] == "9"
    assert added[0]["is_temple"] is False
    assert stats == {
        "fill_added": 1,
        "fill_added_google_open_buildings": 1,
        "fill_skipped_osm": 1,
        "fill_skipped_overlaps_osm": 1,
        "fill_skipped_water": 1,
        "fill_skipped_on_road": 1,
        "fill_skipped_sensitive_ground": 1,
        "fill_skipped_small": 1,
        "fill_skipped_underground": 1,
    }


def test_no_height_is_invented(tmp_path, area: AreaConfig, bounds: MapBounds):
    area = dataclasses.replace(area, building_fill=FILL)
    rows = [_row(bounds, "a", box(50, 10, 60, 20), "Microsoft ML Buildings")]
    layers = _layers(bounds)
    building_fill.fill(layers, area, bounds, _write(tmp_path / "b.parquet", rows))
    properties = layers["buildings"][-1]["properties"]
    assert properties["source_height"] is None
    assert properties["source_levels"] is None
    assert "render_height_m" not in properties


def test_missing_file_or_config_changes_nothing(area: AreaConfig, bounds: MapBounds):
    layers = _layers(bounds)
    assert building_fill.run(layers, area, bounds) == {}
    missing = dataclasses.replace(area, building_fill=dataclasses.replace(FILL, path="nope.pq"))
    assert building_fill.run(layers, missing, bounds) == {}
    assert len(layers["buildings"]) == 1
