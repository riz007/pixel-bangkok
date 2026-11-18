"""OpenStreetMap from a regional PBF extract (e.g. Geofabrik), as an alternative to Overpass.

The PBF is downloaded once into data/raw/_cache/geofabrik/ and checked against
the published MD5. Elements inside the area are selected with the same tag
rules as the Overpass query and written in Overpass JSON shape (WGS84 lon/lat,
ways with `geometry`, relations with member geometries), so later stages are
unchanged.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import shutil
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import osmium
import osmium.filter

log = logging.getLogger(__name__)

USER_AGENT = "osm-area-pipeline/0.1"
CHUNK_BYTES = 1 << 20

Tags = dict[str, str]
BBox = tuple[float, float, float, float]

_GREEN_NATURAL = re.compile(r"^(water|wood|scrub|tree|tree_row)$")
_LEISURE = re.compile(r"^(park|garden|pitch|playground)$")
_LANDUSE = re.compile(
    r"^(grass|forest|meadow|recreation_ground|village_green|religious|residential|commercial"
    r"|retail|education|institutional|military)$"
)
_AMENITY = re.compile(r"^(place_of_worship|parking|school|university|college|hospital)$")
_POI_TOURISM = re.compile(r"^(attraction|museum|gallery|viewpoint)$")
_POI_AMENITY = re.compile(r"^(place_of_worship|ferry_terminal|marketplace|theatre|university)$")
_POI_MAN_MADE = re.compile(r"^(pier|bridge|tower)$")
_POI_BUILDING = re.compile(r"^(temple|palace|government|public|church|mosque)$")
_POI_PLACE = re.compile(r"^(neighbourhood|quarter|suburb)$")
RAIL_KINDS = {"rail", "light_rail", "subway", "monorail", "narrow_gauge", "tram"}
TRANSIT_ROUTES = {"train", "subway", "light_rail", "monorail", "tram"}


def is_transit_route(tags: Tags) -> bool:
    return tags.get("type") == "route" and tags.get("route") in TRANSIT_ROUTES


def matches_map(tags: Tags, kind: str) -> bool:
    """Mirror of extract.build_query: features drawn on the map."""
    if "building" in tags or "building:part" in tags:
        return True
    if kind == "way" and ("highway" in tags or "waterway" in tags or tags.get("route") == "ferry"):
        return True
    if kind == "way" and tags.get("railway") in RAIL_KINDS:
        return True
    if kind == "relation" and is_transit_route(tags):
        return True
    return bool(
        tags.get("man_made") == "pier"
        or _GREEN_NATURAL.match(tags.get("natural", ""))
        or _LEISURE.match(tags.get("leisure", ""))
        or _LANDUSE.match(tags.get("landuse", ""))
        or _AMENITY.match(tags.get("amenity", ""))
        or tags.get("place") == "square"
        or tags.get("historic") in {"castle", "palace"}
    )


def matches_poi(tags: Tags) -> bool:
    """Mirror of pois.build_query: named features with a Wikidata ID."""
    if "wikidata" not in tags or "name" not in tags:
        return False
    return bool(
        _POI_TOURISM.match(tags.get("tourism", ""))
        or "historic" in tags
        or _POI_AMENITY.match(tags.get("amenity", ""))
        or tags.get("railway") == "station"
        or tags.get("leisure") == "park"
        or _POI_MAN_MADE.match(tags.get("man_made", ""))
        or _POI_BUILDING.match(tags.get("building", ""))
        or _POI_PLACE.match(tags.get("place", ""))
    )


def _inside(lon: float, lat: float, bbox: BBox) -> bool:
    west, south, east, north = bbox
    return west <= lon <= east and south <= lat <= north


def _intersects(coords: list[dict[str, float]], bbox: BBox) -> bool:
    if not coords:
        return False
    west, south, east, north = bbox
    lons = [c["lon"] for c in coords]
    lats = [c["lat"] for c in coords]
    return min(lons) <= east and max(lons) >= west and min(lats) <= north and max(lats) >= south


def select_elements(
    pbf: Path,
    bbox: BBox,
    match_map: Callable[[Tags, str], bool] = matches_map,
    match_poi: Callable[[Tags], bool] = matches_poi,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (map elements, POI candidates) intersecting bbox (west, south, east, north)."""
    relations: dict[int, dict[str, Any]] = {}
    member_ways: set[int] = set()
    for relation in osmium.FileProcessor(str(pbf), osmium.osm.RELATION):
        tags = dict(relation.tags)
        if (
            tags.get("type") not in {"multipolygon", None}
            and not match_poi(tags)
            and not is_transit_route(tags)
        ):
            continue
        if not (match_map(tags, "relation") or match_poi(tags)):
            continue
        members = [
            {"type": "way", "ref": member.ref, "role": member.role}
            for member in relation.members
            if member.type == "w"
        ]
        if not members:
            continue
        relations[relation.id] = {
            "type": "relation",
            "id": relation.id,
            "tags": tags,
            "members": members,
        }
        member_ways.update(member["ref"] for member in members)
    log.info("PBF pass 1: %d candidate relations", len(relations))

    tagged_nodes_only = osmium.filter.EmptyTagFilter().enable_for(osmium.osm.NODE)
    processor = (
        osmium.FileProcessor(str(pbf), osmium.osm.NODE | osmium.osm.WAY)
        .with_locations()
        .with_filter(tagged_nodes_only)
    )
    nodes: list[dict[str, Any]] = []
    ways: dict[int, dict[str, Any]] = {}
    way_geometry: dict[int, list[dict[str, float]]] = {}
    for item in processor:
        if item.is_node():
            location = item.location
            if not location.valid() or not _inside(location.lon, location.lat, bbox):
                continue
            tags = dict(item.tags)
            if match_map(tags, "node") or match_poi(tags):
                nodes.append(
                    {
                        "type": "node",
                        "id": item.id,
                        "lat": location.lat,
                        "lon": location.lon,
                        "tags": tags,
                    }
                )
            continue
        wanted_member = item.id in member_ways
        tags = dict(item.tags)
        wanted = match_map(tags, "way") or match_poi(tags)
        if not (wanted or wanted_member):
            continue
        coords = [
            {"lat": node.location.lat, "lon": node.location.lon}
            for node in item.nodes
            if node.location.valid()
        ]
        if wanted_member:
            way_geometry[item.id] = coords
        if wanted and _intersects(coords, bbox):
            ways[item.id] = {"type": "way", "id": item.id, "tags": tags, "geometry": coords}
    log.info("PBF pass 2: %d nodes, %d ways in the area", len(nodes), len(ways))

    kept_relations = []
    for relation in relations.values():
        for member in relation["members"]:
            member["geometry"] = way_geometry.get(member["ref"], [])
        if any(_intersects(member["geometry"], bbox) for member in relation["members"]):
            if is_transit_route(relation["tags"]):
                for member in relation["members"]:
                    member.pop("geometry")
            kept_relations.append(relation)

    elements = nodes + list(ways.values()) + kept_relations
    elements.sort(key=lambda element: (element["type"], element["id"]))
    map_elements = [e for e in elements if match_map(e["tags"], e["type"])]
    poi_elements = [e for e in elements if match_poi(e["tags"])]
    return map_elements, poi_elements


def download(url: str, cache_dir: Path, force: bool = False) -> tuple[Path, dict[str, Any]]:
    """Download a PBF once, verifying the MD5 Geofabrik publishes next to it."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    target = cache_dir / Path(url).name
    meta_path = target.with_suffix(".json")
    if target.exists() and meta_path.exists() and not force:
        return target, json.loads(meta_path.read_text(encoding="utf-8"))
    request = urllib.request.Request(url + ".md5", headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        expected = response.read().decode().split()[0]
    partial = target.with_suffix(".part")
    digest = hashlib.md5()
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    log.info("downloading %s", url)
    with urllib.request.urlopen(request, timeout=120) as response, partial.open("wb") as handle:
        resolved = response.geturl()
        last_modified = response.headers.get("Last-Modified")
        while chunk := response.read(CHUNK_BYTES):
            digest.update(chunk)
            handle.write(chunk)
    if digest.hexdigest() != expected:
        partial.unlink(missing_ok=True)
        raise RuntimeError(f"MD5 mismatch for {url}")
    shutil.move(partial, target)
    metadata = {
        "url": url,
        "resolved_url": resolved,
        "last_modified": last_modified,
        "md5": expected,
        "size_bytes": target.stat().st_size,
        "retrieved_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    meta_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return target, metadata
