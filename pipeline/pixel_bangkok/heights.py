"""Stage 3 (enrich): derive render heights for buildings with explicit provenance.

Order: curated manual override -> source height tag -> building:levels x floor
height -> unknown default. Source values are never overwritten.
"""

from __future__ import annotations

import json
import logging
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import RenderConfig
from .geojson_io import read_feature_collection, write_feature_collection
from .schemas import HeightProvenance, RoofShape

log = logging.getLogger(__name__)

FEET_TO_METRES = 0.3048
_HEIGHT_PATTERN = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(m|metres?|meters?|ft|feet|')?\s*$", re.I)


def parse_height_m(raw: str | None) -> float | None:
    """Parse an OSM `height` value to metres. Unitless values are metres."""
    if raw is None:
        return None
    match = _HEIGHT_PATTERN.match(raw.replace(",", "."))
    if not match:
        return None
    value = float(match.group(1))
    unit = (match.group(2) or "m").lower()
    if unit in {"ft", "feet", "'"}:
        value *= FEET_TO_METRES
    return value if value > 0 else None


def parse_levels(raw: str | None) -> float | None:
    if raw is None:
        return None
    try:
        value = float(raw.strip().replace(",", "."))
    except ValueError:
        return None
    return value if value > 0 else None


@dataclass(frozen=True)
class DerivedHeight:
    render_height_m: float
    provenance: HeightProvenance
    note: str | None = None


def derive_height(
    source_height: str | None,
    source_levels: str | None,
    floor_height_m: float,
    unknown_height_m: float,
    manual: dict[str, Any] | None = None,
) -> DerivedHeight:
    if manual is not None and "height_m" in manual:
        return DerivedHeight(float(manual["height_m"]), "manual", manual.get("note"))
    height = parse_height_m(source_height)
    if height is not None:
        return DerivedHeight(height, "source")
    levels = parse_levels(source_levels)
    if levels is not None:
        return DerivedHeight(
            levels * floor_height_m,
            "estimated",
            f"{levels:g} levels x {floor_height_m:g} m assumed floor height",
        )
    return DerivedHeight(unknown_height_m, "unknown", "no height data; default visual height")


def load_landmark_overrides(curated_dir: Path) -> dict[str, dict[str, Any]]:
    path = curated_dir / "landmarks.json"
    if not path.exists():
        return {}
    records = json.loads(path.read_text(encoding="utf-8"))["landmarks"]
    return {record["source_id"]: record for record in records}


def roof_shape(properties: dict[str, Any], manual: dict[str, Any] | None) -> RoofShape:
    if manual is not None and "roof_shape" in manual:
        return manual["roof_shape"]
    return "spire" if properties.get("is_tower") else "flat"


def run(processed_dir: Path, curated_dir: Path, render: RenderConfig) -> Path:
    collection = read_feature_collection(processed_dir / "buildings.geojson")
    overrides = load_landmark_overrides(curated_dir)
    counts: Counter[str] = Counter()
    unused = set(overrides)
    for feature in collection["features"]:
        properties = feature["properties"]
        manual = overrides.get(properties["source_id"])
        unused.discard(properties["source_id"])
        derived = derive_height(
            properties["source_height"],
            properties["source_levels"],
            render.floor_height_m,
            render.unknown_height_m,
            manual,
        )
        properties["render_height_m"] = round(derived.render_height_m, 2)
        properties["height_provenance"] = derived.provenance
        properties["height_note"] = derived.note
        properties["roof_shape"] = roof_shape(properties, manual)
        counts[derived.provenance] += 1
    for source_id in sorted(unused):
        log.warning("curated landmark override matches no building: %s", source_id)
    metadata = dict(collection["metadata"])
    metadata["height_provenance_counts"] = dict(sorted(counts.items()))
    metadata["floor_height_m"] = render.floor_height_m
    metadata["unknown_height_m"] = render.unknown_height_m
    output = processed_dir / "buildings.enriched.geojson"
    write_feature_collection(output, collection["features"], metadata)
    log.info("height provenance: %s -> %s", dict(counts), output)
    return output
