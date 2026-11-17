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
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

from . import rasters
from .config import AreaConfig
from .crs import MapBounds

log = logging.getLogger(__name__)

USER_AGENT = "osm-area-pipeline/0.1"
QUERY_BUFFER_M = 20.0
ATTEMPTS_PER_ENDPOINT = 3


def build_query(bounds: MapBounds) -> str:
    south, west, north, east = bounds.geographic_bbox(buffer_m=QUERY_BUFFER_M)
    bbox = f"{south:.6f},{west:.6f},{north:.6f},{east:.6f}"
    return f"""[out:json][timeout:90];
(
  nwr["building"]({bbox});
  nwr["building:part"]({bbox});
  way["highway"]({bbox});
  nwr["man_made"="pier"]({bbox});
  nwr["natural"~"^(water|wood|scrub|tree|tree_row)$"]({bbox});
  way["waterway"]({bbox});
  nwr["leisure"~"^(park|garden|pitch|playground)$"]({bbox});
  nwr["landuse"~"^(grass|forest|meadow|recreation_ground|village_green)$"]({bbox});
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


def fetch(area: AreaConfig, query: str, timeout_s: float = 120.0) -> tuple[dict[str, object], str]:
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


def _fetch_osm(area: AreaConfig, bounds: MapBounds, output: Path) -> dict[str, object]:
    query = build_query(bounds)
    payload, endpoint = fetch(area, query)
    output.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    south, west, north, east = bounds.geographic_bbox(buffer_m=QUERY_BUFFER_M)
    metadata = {
        "provider": area.source.provider,
        "dataset": area.source.dataset,
        "licence": area.source.licence,
        "attribution": area.source.attribution,
        "access_method": "Overpass API",
        "endpoint": endpoint,
        "retrieved_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "osm_base_timestamp": (payload.get("osm3s") or {}).get("timestamp_osm_base"),
        "query": query,
        "query_bbox_wgs84": {"south": south, "west": west, "north": north, "east": east},
        "element_count": len(payload["elements"]),
    }
    log.info("wrote %d OSM elements to %s", metadata["element_count"], output)
    return metadata


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
    if osm_path.exists() and not force:
        log.info("raw OSM extract exists, skipping download: %s (use --force)", osm_path)
    else:
        metadata["osm"] = _fetch_osm(area, bounds, osm_path)

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
