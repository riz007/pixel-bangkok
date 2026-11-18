"""Stage 1: download raw source data for an area.

Outputs in data/raw/<area>/:
- osm.json: Overpass JSON, WGS84 lon/lat degrees.
- building_heights.tif, tree_canopy.tif: raster windows on the area grid in the
  area CRS (see rasters.py), when the area config lists those sources.
- extract-metadata.json: provenance for everything above.
"""

from __future__ import annotations

import json
import logging
import math
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

from . import osm_pbf, pois, rasters
from .config import AreaConfig
from .crs import MapBounds

log = logging.getLogger(__name__)

USER_AGENT = "osm-area-pipeline/0.1"
QUERY_BUFFER_M = 20.0
CHUNK_M = 1000.0
ATTEMPTS_PER_ENDPOINT = 3


def build_query(bounds: MapBounds) -> str:
    south, west, north, east = bounds.geographic_bbox(buffer_m=QUERY_BUFFER_M)
    bbox = f"{south:.6f},{west:.6f},{north:.6f},{east:.6f}"
    return f"""[out:json][timeout:240][maxsize:1073741824];
(
  nwr["building"]({bbox});
  nwr["building:part"]({bbox});
  way["highway"]({bbox});
  nwr["man_made"="pier"]({bbox});
  nwr["natural"~"^(water|wood|scrub|tree|tree_row)$"]({bbox});
  way["waterway"]({bbox});
  way["route"="ferry"]({bbox});
  way["railway"~"^(rail|light_rail|subway|monorail|narrow_gauge|tram)$"]({bbox});
  relation["type"="route"]["route"~"^(train|subway|light_rail|monorail|tram)$"]({bbox});
  nwr["leisure"~"^(park|garden|pitch|playground)$"]({bbox});
  nwr["landuse"~"^(grass|forest|meadow|recreation_ground|village_green)$"]({bbox});
  nwr["landuse"~"^(religious|residential|commercial|retail|education|institutional|military)$"]({bbox});
  nwr["amenity"~"^(place_of_worship|parking|school|university|college|hospital)$"]({bbox});
  nwr["place"="square"]({bbox});
  nwr["historic"~"^(castle|palace)$"]({bbox});
);
out body geom;
"""


def _post(endpoint: str, query: str, timeout_s: float) -> dict[str, object]:
    body = urllib.parse.urlencode({"data": query}).encode()
    request = urllib.request.Request(endpoint, data=body, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout_s) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict) or "elements" not in payload:
        raise ValueError("Overpass response has no 'elements'")
    return payload


def fetch(area: AreaConfig, query: str, timeout_s: float = 300.0) -> tuple[dict[str, object], str]:
    errors: list[str] = []
    for endpoint in area.source.overpass_endpoints:
        for attempt in range(ATTEMPTS_PER_ENDPOINT):
            try:
                return _post(endpoint, query, timeout_s), endpoint
            except (urllib.error.URLError, TimeoutError, ValueError) as exc:
                wait_s = 5 * 2**attempt
                errors.append(f"{endpoint}: {exc}")
                log.warning("Overpass request failed (%s); retrying in %ss", exc, wait_s)
                time.sleep(wait_s)
    raise RuntimeError("all Overpass endpoints failed:\n" + "\n".join(errors))


def chunk_bounds(bounds: MapBounds, chunk_m: float = CHUNK_M) -> list[tuple[str, MapBounds]]:
    """Split the area into named sub-rectangles no larger than chunk_m on a side."""
    columns = max(1, math.ceil(bounds.width_m / chunk_m))
    rows = max(1, math.ceil(bounds.height_m / chunk_m))
    width, height = bounds.width_m / columns, bounds.height_m / rows
    return [
        (
            f"{column}_{row}",
            MapBounds(
                crs=bounds.crs,
                origin_easting=bounds.origin_easting + column * width,
                origin_northing=bounds.origin_northing + row * height,
                width_m=width,
                height_m=height,
            ),
        )
        for row in range(rows)
        for column in range(columns)
    ]


def merge_elements(payloads: list[dict[str, object]]) -> list[dict[str, object]]:
    merged: dict[tuple[str, int], dict[str, object]] = {}
    for payload in payloads:
        for element in payload["elements"]:
            merged.setdefault((element["type"], element["id"]), element)
    return [merged[key] for key in sorted(merged)]


def _fetch_osm(area: AreaConfig, bounds: MapBounds, output: Path) -> dict[str, object]:
    chunk_dir = output.parent / "osm-chunks"
    chunk_dir.mkdir(parents=True, exist_ok=True)
    payloads = []
    endpoints = {}
    for name, chunk in chunk_bounds(bounds):
        chunk_path = chunk_dir / f"{name}.json"
        if chunk_path.exists():
            payload = json.loads(chunk_path.read_text(encoding="utf-8"))
        else:
            payload, endpoints[name] = fetch(area, build_query(chunk))
            chunk_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            log.info("chunk %s: %d elements", name, len(payload["elements"]))
        payloads.append(payload)
    elements = merge_elements(payloads)
    timestamps = sorted(
        stamp
        for payload in payloads
        if (stamp := (payload.get("osm3s") or {}).get("timestamp_osm_base"))
    )
    output.write_text(
        json.dumps(
            {
                "osm3s": {"timestamp_osm_base": timestamps[0] if timestamps else None},
                "elements": elements,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    south, west, north, east = bounds.geographic_bbox(buffer_m=QUERY_BUFFER_M)
    metadata = {
        "provider": area.source.provider,
        "dataset": area.source.dataset,
        "licence": area.source.licence,
        "attribution": area.source.attribution,
        "access_method": "Overpass API",
        "endpoints": endpoints,
        "chunks": len(payloads),
        "retrieved_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "osm_base_timestamp": timestamps[0] if timestamps else None,
        "osm_base_timestamp_latest": timestamps[-1] if timestamps else None,
        "query": build_query(bounds),
        "query_bbox_wgs84": {"south": south, "west": west, "north": north, "east": east},
        "element_count": len(elements),
    }
    log.info("wrote %d OSM elements from %d chunks to %s", len(elements), len(payloads), output)
    return metadata


def _extract_pbf(
    area: AreaConfig,
    bounds: MapBounds,
    osm_path: Path,
    poi_path: Path,
    raw_dir: Path,
    force: bool,
) -> dict[str, object]:
    assert area.source.extract_url is not None
    pbf, download = osm_pbf.download(
        area.source.extract_url, raw_dir.parent / "_cache" / "pbf", force=force
    )
    south, west, north, east = bounds.geographic_bbox(buffer_m=QUERY_BUFFER_M)
    elements, poi_elements = osm_pbf.select_elements(pbf, (west, south, east, north))
    osm_path.write_text(json.dumps({"elements": elements}, ensure_ascii=False), encoding="utf-8")
    poi_path.write_text(
        json.dumps({"elements": poi_elements}, ensure_ascii=False), encoding="utf-8"
    )
    log.info("wrote %d map and %d POI elements from %s", len(elements), len(poi_elements), pbf)
    common = {
        "provider": area.source.provider,
        "dataset": area.source.dataset,
        "licence": area.source.licence,
        "attribution": area.source.attribution,
        "access_method": "regional PBF extract read with pyosmium",
        "extract": download,
        "retrieved_at": download["retrieved_at"],
        "osm_base_timestamp": download.get("last_modified"),
        "query_bbox_wgs84": {"south": south, "west": west, "north": north, "east": east},
    }
    return {
        "osm": {**common, "element_count": len(elements)},
        "poi_candidates": {**common, "element_count": len(poi_elements)},
    }


def run(area: AreaConfig, raw_dir: Path, force: bool = False) -> Path:
    bounds = MapBounds.from_area(area)
    raw_dir.mkdir(parents=True, exist_ok=True)
    metadata_path = raw_dir / "extract-metadata.json"
    metadata = (
        json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.exists() else {}
    )
    if "osm" not in metadata and "provider" in metadata:
        metadata = {"osm": metadata}

    osm_path = raw_dir / "osm.json"
    poi_path = raw_dir / "poi-candidates.json"
    if osm_path.exists() and poi_path.exists() and not force:
        log.info("raw OSM extract exists, skipping download: %s (use --force)", osm_path)
    elif area.source.method == "pbf":
        metadata.update(_extract_pbf(area, bounds, osm_path, poi_path, raw_dir, force))
    elif force or not osm_path.exists():
        metadata["osm"] = _fetch_osm(area, bounds, osm_path)

    if area.source.method == "overpass" and (force or not poi_path.exists()):
        south, west, north, east = bounds.geographic_bbox()
        payload, endpoint = fetch(
            area, pois.build_query(f"{south:.6f},{west:.6f},{north:.6f},{east:.6f}")
        )
        poi_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        metadata["poi_candidates"] = {
            "endpoint": endpoint,
            "retrieved_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "element_count": len(payload["elements"]),
        }
        log.info("wrote %d POI candidates to %s", len(payload["elements"]), poi_path)

    heights_path = raw_dir / "building_heights.tif"
    if area.building_heights is not None and (force or not heights_path.exists()):
        metadata["building_heights"] = rasters.fetch_building_heights(
            bounds,
            area.building_heights,
            heights_path,
            raw_dir.parent / "_cache" / "open-buildings",
        )
    canopy_path = raw_dir / "tree_canopy.tif"
    if area.tree_canopy is not None and (force or not canopy_path.exists()):
        metadata["tree_canopy"] = rasters.fetch_tree_canopy(bounds, area.tree_canopy, canopy_path)

    metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
    return metadata_path
