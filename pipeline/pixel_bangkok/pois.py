"""Landmark POIs from OpenStreetMap features that carry a Wikidata ID.

Inputs:
- data/raw/<area>/poi-candidates.json: Overpass JSON (WGS84) of named features with
  `wikidata` tags, fetched by the extract stage.
- data/raw/<area>/wikidata.json: cached Wikidata labels, descriptions and sitelinks
  (CC0), fetched here on first run.

Output: data/processed/<area>/pois.json in the same shape as curated POI files.
Each POI's point lies on its OSM feature; names and descriptions are copied from
OSM and Wikidata, never written by hand.
"""

from __future__ import annotations

import json
import logging
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from shapely.geometry import LineString, Point, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.ops import polygonize, unary_union

from .config import AreaConfig
from .crs import MapBounds

log = logging.getLogger(__name__)

WIKIDATA_API = "https://www.wikidata.org/w/api.php"
USER_AGENT = "osm-area-pipeline/0.1 (map POI enrichment)"
BATCH_SIZE = 50
BATCH_PAUSE_S = 1.0
BACKOFF_S = 15.0
MAX_ATTEMPTS = 5
MIN_POIS = 40
POIS_PER_KM2 = 1.5
_QID = re.compile(r"^Q\d+$")
_STATION_CODE = re.compile(r"^([A-Z]+)\d*$")
SRT_OPERATOR = "การรถไฟแห่งประเทศไทย"
# Official station-code prefixes (OSM `ref`) and the lines they belong to.
LINES = {
    "CEN": ("BTS Sukhumvit and Silom lines", "รถไฟฟ้าบีทีเอส สายสุขุมวิทและสายสีลม"),
    "N": ("BTS Sukhumvit Line", "รถไฟฟ้าบีทีเอส สายสุขุมวิท"),
    "E": ("BTS Sukhumvit Line", "รถไฟฟ้าบีทีเอส สายสุขุมวิท"),
    "S": ("BTS Silom Line", "รถไฟฟ้าบีทีเอส สายสีลม"),
    "W": ("BTS Silom Line", "รถไฟฟ้าบีทีเอส สายสีลม"),
    "G": ("Gold Line", "รถไฟฟ้าสายสีทอง"),
    "BL": ("MRT Blue Line", "รถไฟฟ้ามหานคร สายสีน้ำเงิน"),
    "PP": ("MRT Purple Line", "รถไฟฟ้ามหานคร สายสีม่วง"),
    "YL": ("MRT Yellow Line", "รถไฟฟ้ามหานคร สายสีเหลือง"),
    "PK": ("MRT Pink Line", "รถไฟฟ้ามหานคร สายสีชมพู"),
    "A": ("Airport Rail Link", "รถไฟฟ้าแอร์พอร์ต เรล ลิงก์"),
    "RN": ("SRT Dark Red Line", "รถไฟฟ้าสายสีแดงเข้ม"),
    "RW": ("SRT Light Red Line", "รถไฟฟ้าสายสีแดงอ่อน"),
}


def build_query(bbox: str) -> str:
    selectors = [
        'nwr["wikidata"]["name"]["tourism"~"^(attraction|museum|gallery|viewpoint)$"]',
        'nwr["wikidata"]["name"]["historic"]',
        'nwr["wikidata"]["name"]["amenity"~"^(place_of_worship|ferry_terminal|marketplace|theatre|university)$"]',
        'nwr["wikidata"]["name"]["railway"="station"]',
        'nwr["wikidata"]["name"]["leisure"="park"]',
        'nwr["wikidata"]["name"]["man_made"~"^(pier|bridge|tower)$"]',
        'nwr["wikidata"]["name"]["building"~"^(temple|palace|government|public|church|mosque)$"]',
        'nwr["wikidata"]["name"]["place"~"^(neighbourhood|quarter|suburb)$"]',
    ]
    body = "\n".join(f"  {selector}({bbox});" for selector in selectors)
    return f"[out:json][timeout:120];\n(\n{body}\n);\nout tags geom;\n"


def category(tags: dict[str, str]) -> str:
    if tags.get("railway") == "station":
        return "transit"
    if tags.get("amenity") == "ferry_terminal" or tags.get("man_made") == "pier":
        return "pier"
    if tags.get("tourism") in {"museum", "gallery"}:
        return "museum"
    if tags.get("amenity") == "place_of_worship" or tags.get("building") in {
        "temple",
        "church",
        "mosque",
    }:
        return "temple"
    if tags.get("leisure") == "park":
        return "park"
    if tags.get("amenity") == "marketplace":
        return "market"
    if "place" in tags:
        return "neighbourhood"
    if "historic" in tags:
        return "historic"
    return "landmark"


def station_line(tags: dict[str, str]) -> dict[str, str] | None:
    """Line names and station code from the OSM `ref` code, or the SRT operator."""
    if tags.get("railway") != "station":
        return None
    for ref in (tags.get("ref") or "").split(";"):
        match = _STATION_CODE.match(ref.strip())
        if match and match.group(1) in LINES:
            en, th = LINES[match.group(1)]
            return {"en": en, "th": th, "code": ref.strip()}
    if SRT_OPERATOR in (tags.get("operator", ""), tags.get("network", "")):
        return {"en": "State Railway of Thailand", "th": SRT_OPERATOR, "code": ""}
    return None


def anchor_point(element: dict[str, Any]) -> tuple[float, float] | None:
    """A WGS84 (lon, lat) point guaranteed to lie on the element's geometry."""
    if element["type"] == "node":
        return element["lon"], element["lat"]
    geometry: BaseGeometry | None = None
    if element["type"] == "way" and element.get("geometry"):
        coords = [(p["lon"], p["lat"]) for p in element["geometry"]]
        if len(coords) >= 4 and coords[0] == coords[-1]:
            geometry = Polygon(coords)
        elif len(coords) >= 2:
            line = LineString(coords)
            geometry = line.interpolate(0.5, normalized=True)
    elif element["type"] == "relation":
        lines = [
            LineString([(p["lon"], p["lat"]) for p in member["geometry"]])
            for member in element.get("members", [])
            if member.get("type") == "way"
            and member.get("role") in ("outer", "")
            and len(member.get("geometry") or []) >= 2
        ]
        if lines:
            polygons = list(polygonize(unary_union(lines)))
            geometry = unary_union(polygons) if polygons else unary_union(lines)
    if geometry is None or geometry.is_empty:
        return None
    if not geometry.is_valid:
        geometry = geometry.buffer(0)
    point = geometry if isinstance(geometry, Point) else geometry.representative_point()
    return point.x, point.y


def fetch_wikidata(qids: list[str], cache_path: Path) -> dict[str, Any]:
    cache: dict[str, Any] = (
        json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    )
    missing = sorted(qid for qid in set(qids) if qid not in cache)
    for start in range(0, len(missing), BATCH_SIZE):
        batch = missing[start : start + BATCH_SIZE]
        query = urllib.parse.urlencode(
            {
                "action": "wbgetentities",
                "ids": "|".join(batch),
                "props": "labels|descriptions|sitelinks",
                "languages": "en|th",
                "format": "json",
            }
        )
        entities = _get_entities(f"{WIKIDATA_API}?{query}")
        for qid in batch:
            entity = entities.get(qid, {})
            sitelinks = entity.get("sitelinks", {})
            cache[qid] = {
                "label_en": entity.get("labels", {}).get("en", {}).get("value"),
                "label_th": entity.get("labels", {}).get("th", {}).get("value"),
                "description_en": entity.get("descriptions", {}).get("en", {}).get("value"),
                "enwiki": sitelinks.get("enwiki", {}).get("title"),
                "sitelinks": len(sitelinks),
            }
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8")
        time.sleep(BATCH_PAUSE_S)
    return cache


def _get_entities(url: str) -> dict[str, Any]:
    """GET with polite retries: honours Retry-After on 429 and backs off on 5xx."""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.loads(response.read().decode("utf-8")).get("entities", {})
        except urllib.error.HTTPError as error:
            if error.code != 429 and error.code < 500 or attempt == MAX_ATTEMPTS:
                raise
            retry_after = error.headers.get("Retry-After", "")
            wait = float(retry_after) if retry_after.isdigit() else BACKOFF_S * attempt
            log.warning("Wikidata answered %d; retrying in %.0fs", error.code, wait)
            time.sleep(wait)
    raise RuntimeError("unreachable")


def _source_url(qid: str, enwiki: str | None) -> str:
    if enwiki:
        return "https://en.wikipedia.org/wiki/" + urllib.parse.quote(enwiki.replace(" ", "_"))
    return f"https://www.wikidata.org/wiki/{qid}"


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def build_pois(
    elements: list[dict[str, Any]],
    wikidata: dict[str, Any],
    bounds: MapBounds,
    limit: int = MIN_POIS,
) -> list[dict[str, Any]]:
    by_qid: dict[str, dict[str, Any]] = {}
    for element in sorted(elements, key=lambda item: (item["type"], item["id"])):
        tags = element.get("tags", {})
        qid = tags.get("wikidata", "")
        if not _QID.match(qid):
            continue
        point = anchor_point(element)
        if point is None or not bounds.contains_world(*bounds.lonlat_to_world(*point)):
            continue
        info = wikidata.get(qid) or {}
        name_en = tags.get("name:en") or info.get("label_en")
        if not name_en:
            continue
        candidate = {
            "id": _slug(name_en) or qid.lower(),
            "name_en": name_en,
            "name_th": tags.get("name:th") or info.get("label_th") or tags.get("name"),
            "aliases": sorted(
                {
                    value
                    for key in ("name", "alt_name", "alt_name:en", "old_name", "short_name")
                    for value in (tags.get(key) or "").split(";")
                    if value and value != name_en
                }
            ),
            "category": category(tags),
            "lon": round(point[0], 6),
            "lat": round(point[1], 6),
            "description": info.get("description_en") or "",
            "source": f"OpenStreetMap {element['type']} {element['id']}; Wikidata {qid}",
            "source_url": _source_url(qid, info.get("enwiki")),
            "_rank": info.get("sitelinks", 0),
        }
        line = station_line(tags)
        if line:
            candidate["line"] = line
            candidate["aliases"] = sorted(
                set(candidate["aliases"]) | {line["en"], line["th"]} | ({line["code"]} - {""})
            )
        existing = by_qid.get(qid)
        if existing is None or (element["type"] != "node" and existing["_rank_type"] == "node"):
            candidate["_rank_type"] = element["type"]
            if existing and "line" in existing and "line" not in candidate:
                candidate["line"] = existing["line"]
                candidate["aliases"] = sorted(set(candidate["aliases"]) | set(existing["aliases"]))
            by_qid[qid] = candidate
        elif "line" in candidate and "line" not in existing:
            existing["line"] = candidate["line"]
            existing["aliases"] = sorted(set(existing["aliases"]) | set(candidate["aliases"]))
    ranked = sorted(by_qid.values(), key=lambda item: (-item["_rank"], item["name_en"]))[:limit]
    seen: set[str] = set()
    pois = []
    for poi in ranked:
        base = poi["id"]
        suffix = 2
        while poi["id"] in seen:
            poi["id"] = f"{base}-{suffix}"
            suffix += 1
        seen.add(poi["id"])
        record = {key: value for key, value in poi.items() if not key.startswith("_")}
        record["rank"] = poi["_rank"]
        pois.append(record)
    return sorted(pois, key=lambda item: item["id"])


def run(area: AreaConfig, raw_dir: Path, processed_dir: Path) -> Path:
    candidates_path = raw_dir / "poi-candidates.json"
    if not candidates_path.exists():
        raise FileNotFoundError(f"{candidates_path} not found; run the extract stage first")
    elements = json.loads(candidates_path.read_text(encoding="utf-8"))["elements"]
    qids = [
        element["tags"]["wikidata"]
        for element in elements
        if _QID.match(element.get("tags", {}).get("wikidata", ""))
    ]
    wikidata = fetch_wikidata(qids, raw_dir / "wikidata.json")
    limit = max(MIN_POIS, round(area.width_m * area.height_m / 1e6 * POIS_PER_KM2))
    pois = build_pois(elements, wikidata, MapBounds.from_area(area), limit)
    output = processed_dir / "pois.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            {
                "description": "Generated from OpenStreetMap (ODbL) and Wikidata (CC0); "
                "ranked by Wikipedia sitelink count.",
                "pois": pois,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    log.info("wrote %d landmark POIs from %d candidates to %s", len(pois), len(elements), output)
    return output
