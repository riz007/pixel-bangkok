"""Optional stage: AI repaint of the procedural map, window by window.

Not part of `all`; the procedural map stays the published default and the
geometry reference. Model: Qwen-Image 2.1 Turbo via mflux, run by
experiments/mflux_worker.py in the mflux tool environment (research licence,
non-commercial use only).

build/<area>/ai/
  plan.json           windows in processing order
  state.json          per-window result: accepted / rejected + drift metrics
  windows/<id>.in.png  procedural input crop
  windows/<id>.raw.png model output
  windows/<id>.png     accepted output after palette snapping
build/<area>/blocks/ai_master_*.png, ai_overlay_*.png  composed blocks
"""

from __future__ import annotations

import json
import logging
import math
import os
import subprocess
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from . import drift
from .blocks import blocks_of, read_info, read_region
from .config import AreaConfig, RenderConfig
from .crs import MapBounds
from .projection import IsoProjection
from .render import parse_color

log = logging.getLogger(__name__)

WINDOW_PX = 1024
STRIDE_PX = 768
FEATHER_PX = WINDOW_PX - STRIDE_PX
PRESERVE_WEIGHT = 0.5
MAX_BACKGROUND_FRACTION = 0.6
PALETTE_COLOURS = 64
STRENGTH = 0.85
RETRY_STRENGTH = 0.7
MAX_ATTEMPTS = 2
STEPS = 8
QUANTIZE = 4
SEED = 20261118
MODEL = "Qwen-Image 2.1 Turbo (mflux, 4-bit, small text encoder)"
LICENCE = "Qwen Research License: non-commercial research and evaluation only"
PROMPT = (
    "Redraw this aerial view as detailed isometric pixel art of a dense Bangkok city: crisp "
    "pixel edges, limited palette, small windows, rooftop clutter, trees, cars and boats. "
    "Keep every building, road, river and tree exactly where it is with the same shapes. "
    "No text."
)
WORKER = Path(__file__).resolve().parents[1] / "experiments" / "mflux_worker.py"
DEFAULT_MFLUX_PYTHON = Path.home() / ".local/share/uv/tools/mflux/bin/python"


@dataclass(frozen=True)
class Window:
    id: str
    left: int
    top: int

    @property
    def box(self) -> tuple[int, int, int, int]:
        return (self.left, self.top, self.left + WINDOW_PX, self.top + WINDOW_PX)


def window_positions(width: int, height: int) -> list[tuple[int, int]]:
    def starts(length: int) -> list[int]:
        if length <= WINDOW_PX:
            return [0]
        values = list(range(0, length - WINDOW_PX + 1, STRIDE_PX))
        if values[-1] != length - WINDOW_PX:
            values.append(length - WINDOW_PX)
        return values

    return [(left, top) for top in starts(height) for left in starts(width)]


def plan(
    area: AreaConfig, render: RenderConfig, build_dir: Path, focus: tuple[float, float]
) -> Path:
    blocks_dir = build_dir / "blocks"
    info = read_info(blocks_dir)
    bounds = MapBounds.from_area(area)
    projection = IsoProjection.create(bounds, render)
    fx, fy = projection.world_to_native(*bounds.lonlat_to_world(*focus))
    background = np.array(Image.new("RGB", (1, 1), render.palette["background"]).getpixel((0, 0)))
    windows = []
    for left, top in window_positions(info["width"], info["height"]):
        crop = np.asarray(
            read_region(blocks_dir, "master", (left, top, left + WINDOW_PX, top + WINDOW_PX), "RGB")
        )
        empty = float(np.all(crop == background, axis=-1).mean())
        if empty > MAX_BACKGROUND_FRACTION:
            continue
        centre = (left + WINDOW_PX / 2, top + WINDOW_PX / 2)
        windows.append(
            {
                "id": f"{left}_{top}",
                "left": left,
                "top": top,
                "distance": math.dist(centre, (fx, fy)),
            }
        )
    windows.sort(key=lambda window: (window["distance"], window["id"]))
    output = build_dir / "ai" / "plan.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"focus": focus, "windows": windows}, indent=1), encoding="utf-8")
    log.info("planned %d AI windows (focus %s) -> %s", len(windows), focus, output)
    return output


def snap_palette(image: Image.Image, colours: int = PALETTE_COLOURS) -> Image.Image:
    """Limit a model output to a small palette with no dithering, for a pixel-art finish."""
    return (
        image.convert("RGB")
        .quantize(colors=colours, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
        .convert("RGB")
    )


def _load_state(ai_dir: Path) -> dict[str, Any]:
    path = ai_dir / "state.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"windows": {}}


def _save_state(ai_dir: Path, state: dict[str, Any]) -> None:
    path = ai_dir / "state.json"
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, indent=1), encoding="utf-8")
    temporary.replace(path)


def judge(reference: Image.Image, raw: Image.Image) -> tuple[Image.Image, dict[str, Any]]:
    """Snap to a palette, undo a small uniform offset, then measure drift against the input."""
    snapped = snap_palette(raw.convert("RGB").resize(reference.size, Image.Resampling.LANCZOS))
    aligned, dx, dy = drift.register(reference, snapped)
    metrics = drift.drift(reference, aligned)
    metrics["registered_px"] = [dx, dy]
    return aligned, metrics


WINDOW_FILES = (".in.png", ".png", ".raw.png", ".cond.png", ".mask.png")
MAX_CHANGED_PX = 32


def invalidate(build_dir: Path) -> list[str]:
    """Drop windows whose procedural input changed by more than MAX_CHANGED_PX pixels.

    Their files move to windows/stale/ and the windows become pending again, so AI art is never
    composed over geometry that has since changed (for example newly drawn viaducts).
    """
    ai_dir = build_dir / "ai"
    blocks_dir = build_dir / "blocks"
    windows_dir = ai_dir / "windows"
    state = _load_state(ai_dir)
    stale = []
    for window_id, entry in sorted(state.get("windows", {}).items()):
        source = windows_dir / f"{window_id}.in.png"
        if not source.exists():
            continue
        box = (entry["left"], entry["top"], entry["left"] + WINDOW_PX, entry["top"] + WINDOW_PX)
        current = np.asarray(read_region(blocks_dir, "master", box, "RGB"))
        with Image.open(source) as image:
            changed = np.any(np.asarray(image.convert("RGB")) != current, axis=-1)
        if int(changed.sum()) <= MAX_CHANGED_PX:
            continue
        stale.append(window_id)
    if not stale:
        return []
    archive = windows_dir / "stale"
    archive.mkdir(exist_ok=True)
    for window_id in stale:
        for suffix in WINDOW_FILES:
            path = windows_dir / f"{window_id}{suffix}"
            if path.exists():
                path.replace(archive / path.name)
        del state["windows"][window_id]
    _save_state(ai_dir, state)
    log.info("%d AI windows no longer match the render and were queued again", len(stale))
    return stale


def run(build_dir: Path, limit: int, batch: int = 8) -> dict[str, int]:
    """Process up to `limit` pending windows in batches; safe to stop and resume."""
    invalidate(build_dir)
    ai_dir = build_dir / "ai"
    blocks_dir = build_dir / "blocks"
    windows = json.loads((ai_dir / "plan.json").read_text(encoding="utf-8"))["windows"]
    info = read_info(blocks_dir)
    state = _load_state(ai_dir)
    state.update(
        {"model": MODEL, "licence": LICENCE, "prompt": PROMPT, "strength": STRENGTH, "steps": STEPS}
    )

    def attempts(window_id: str) -> int:
        entry = state["windows"].get(window_id)
        return 0 if entry is None else int(entry.get("attempts", 1))

    pending = [
        w
        for w in windows
        if w["id"] not in state["windows"]
        or (not state["windows"][w["id"]]["accepted"] and attempts(w["id"]) < MAX_ATTEMPTS)
    ][:limit]
    python = Path(os.environ.get("PIXEL_BANGKOK_MFLUX_PYTHON", DEFAULT_MFLUX_PYTHON))
    if pending and not python.exists():
        raise FileNotFoundError(f"mflux python not found at {python}; `uv tool install mflux`")
    windows_dir = ai_dir / "windows"
    windows_dir.mkdir(parents=True, exist_ok=True)
    (ai_dir / "prompt.txt").write_text(PROMPT, encoding="utf-8")
    counts = {"accepted": 0, "rejected": 0}
    for start in range(0, len(pending), batch):
        chunk = pending[start : start + batch]
        jobs = []
        for window in chunk:
            box = (
                window["left"],
                window["top"],
                window["left"] + WINDOW_PX,
                window["top"] + WINDOW_PX,
            )
            source = windows_dir / f"{window['id']}.in.png"
            if not source.exists():
                read_region(blocks_dir, "master", box, "RGB").save(source)
            with Image.open(source) as procedural:
                conditioned = condition_on_neighbours(
                    ai_dir, state, window, procedural, (info["width"], info["height"])
                )
            model_input, mask_path = source, None
            if conditioned is not None:
                model_input = windows_dir / f"{window['id']}.cond.png"
                mask_path = windows_dir / f"{window['id']}.mask.png"
                conditioned[0].save(model_input)
                conditioned[1].save(mask_path)
            attempt = attempts(window["id"]) + 1
            raw_path = windows_dir / f"{window['id']}.raw.png"
            if attempt > 1 and raw_path.exists():
                raw_path.unlink()
            jobs.append(
                {
                    "input": str(model_input),
                    "mask": str(mask_path) if mask_path else None,
                    "output": str(raw_path),
                    "seed": SEED + attempt - 1,
                    "strength": STRENGTH if attempt == 1 else RETRY_STRENGTH,
                    "attempt": attempt,
                }
            )
        jobs_path = ai_dir / "jobs.jsonl"
        jobs_path.write_text("\n".join(json.dumps(job) for job in jobs), encoding="utf-8")
        began = time.monotonic()
        subprocess.run(
            [
                str(python),
                str(WORKER),
                str(jobs_path),
                "--quantize",
                str(QUANTIZE),
                "--steps",
                str(STEPS),
                "--prompt-file",
                str(ai_dir / "prompt.txt"),
            ],
            check=True,
            env={**os.environ, "HF_HUB_DISABLE_XET": "1"},
        )
        seconds = (time.monotonic() - began) / max(len(chunk), 1)
        for window, job in zip(chunk, jobs, strict=True):
            with (
                Image.open(windows_dir / f"{window['id']}.in.png") as reference,
                Image.open(windows_dir / f"{window['id']}.raw.png") as raw,
            ):
                snapped, metrics = judge(reference.convert("RGB"), raw)
            accepted = bool(metrics["passes"])
            if accepted:
                snapped.save(windows_dir / f"{window['id']}.png")
            state["windows"][window["id"]] = {
                "left": window["left"],
                "top": window["top"],
                "accepted": accepted,
                "attempts": job["attempt"],
                "strength": job["strength"],
                "seconds": round(seconds, 1),
                "finished_at": datetime.now(UTC).isoformat(timespec="seconds"),
                **metrics,
            }
            counts["accepted" if accepted else "rejected"] += 1
        _save_state(ai_dir, state)
        done = len(state["windows"])
        log.info(
            "AI windows: %d/%d done (%d accepted, %d rejected this run), %.0fs per window",
            done,
            len(windows),
            counts["accepted"],
            counts["rejected"],
            seconds,
        )
    return counts


def feather(size: int, feather_px: int, open_start: bool, open_end: bool) -> np.ndarray:
    """1-D weights: linear ramps over `feather_px` at ends that neighbour other windows."""
    weights = np.ones(size, dtype=np.float32)
    ramp = (np.arange(feather_px, dtype=np.float32) + 0.5) / feather_px
    if not open_start:
        weights[:feather_px] = np.minimum(weights[:feather_px], ramp)
    if not open_end:
        weights[-feather_px:] = np.minimum(weights[-feather_px:], ramp[::-1])
    return weights


def blend_region(
    ai_dir: Path,
    accepted: list[tuple[str, dict[str, Any]]],
    box: tuple[int, int, int, int],
    image_size: tuple[int, int],
) -> tuple[np.ndarray, np.ndarray]:
    """Feather-weighted sum of accepted AI windows over `box`, and the summed weights."""
    left_box, top_box, right_box, bottom_box = box
    width, height = image_size
    total = np.zeros((bottom_box - top_box, right_box - left_box), dtype=np.float32)
    blended = np.zeros((*total.shape, 3), dtype=np.float32)
    for window_id, entry in accepted:
        left, top = entry["left"], entry["top"]
        x0, y0 = max(left, left_box), max(top, top_box)
        x1 = min(left + WINDOW_PX, right_box)
        y1 = min(top + WINDOW_PX, bottom_box)
        if x0 >= x1 or y0 >= y1:
            continue
        with Image.open(ai_dir / "windows" / f"{window_id}.png") as image:
            ai = np.asarray(image.convert("RGB"), dtype=np.float32)
        weight = np.outer(
            feather(WINDOW_PX, FEATHER_PX, top == 0, top + WINDOW_PX >= height),
            feather(WINDOW_PX, FEATHER_PX, left == 0, left + WINDOW_PX >= width),
        )
        ws = weight[y0 - top : y1 - top, x0 - left : x1 - left]
        total[y0 - top_box : y1 - top_box, x0 - left_box : x1 - left_box] += ws
        blended[y0 - top_box : y1 - top_box, x0 - left_box : x1 - left_box] += (
            ai[y0 - top : y1 - top, x0 - left : x1 - left] * ws[..., None]
        )
    return blended, total


def mix(procedural: np.ndarray, blended: np.ndarray, total: np.ndarray) -> np.ndarray:
    alpha = np.clip(total, 0, 1)[..., None]
    ai = np.where(total[..., None] > 0, blended / np.maximum(total, 1e-6)[..., None], 0)
    return (ai * alpha + procedural * (1 - alpha)).round().clip(0, 255).astype(np.uint8)


def _accepted(ai_dir: Path, state: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    return [
        (window_id, entry)
        for window_id, entry in sorted(state["windows"].items())
        if entry["accepted"] and (ai_dir / "windows" / f"{window_id}.png").exists()
    ]


def condition_on_neighbours(
    ai_dir: Path,
    state: dict[str, Any],
    window: dict[str, Any],
    procedural: Image.Image,
    image_size: tuple[int, int],
) -> tuple[Image.Image, Image.Image] | None:
    """Input with finished neighbours painted into the overlap, plus an inpaint mask.

    Mask: black (keep) where neighbour coverage is at least PRESERVE_WEIGHT, white (repaint)
    elsewhere. Returns None when no accepted neighbour overlaps the window.
    """
    others = [item for item in _accepted(ai_dir, state) if item[0] != window["id"]]
    box = (window["left"], window["top"], window["left"] + WINDOW_PX, window["top"] + WINDOW_PX)
    blended, total = blend_region(ai_dir, others, box, image_size)
    if not np.any(total > 0):
        return None
    conditioned = mix(np.asarray(procedural.convert("RGB"), dtype=np.float32), blended, total)
    mask = np.where(total >= PRESERVE_WEIGHT, 0, 255).astype(np.uint8)
    return Image.fromarray(conditioned, "RGB"), Image.fromarray(mask, "L")


def compose(
    render: RenderConfig, build_dir: Path, area: AreaConfig | None = None
) -> dict[str, Any]:
    """Blend accepted windows over the procedural master, block by block."""
    from .pixelart import edge_dissolve

    invalidate(build_dir)
    ai_dir = build_dir / "ai"
    blocks_dir = build_dir / "blocks"
    info = read_info(blocks_dir)
    state = _load_state(ai_dir)
    accepted = _accepted(ai_dir, state)
    covered = 0
    size = (info["width"], info["height"])
    for block in blocks_of(info):
        with Image.open(blocks_dir / f"master_{block.name}.png") as image:
            procedural = np.asarray(image.convert("RGB"), dtype=np.float32)
        box = (block.left, block.top, block.left + block.width, block.top + block.height)
        blended, total = blend_region(ai_dir, accepted, box, size)
        result = mix(procedural, blended, total)
        dissolve = (
            edge_dissolve(MapBounds.from_area(area), render, box)
            if area is not None
            else np.zeros(result.shape[:2], dtype=bool)
        )
        result[dissolve] = np.array(parse_color(render.palette["background"])[:3], np.uint8)
        covered += int(np.count_nonzero(total > 0))
        master = Image.fromarray(result, "RGB")
        master.save(blocks_dir / f"ai_master_{block.name}.png")
        with Image.open(blocks_dir / f"occlusion_{block.name}.png") as occlusion:
            mask = np.asarray(occlusion.convert("1")) | dissolve
        rgba = np.dstack([result, np.where(mask, 255, 0).astype(np.uint8)])
        Image.fromarray(rgba, "RGBA").save(blocks_dir / f"ai_overlay_{block.name}.png")
        front_path = blocks_dir / f"front_{block.name}.png"
        if front_path.exists():
            with Image.open(front_path) as front:
                front_mask = np.asarray(front.convert("1")) | dissolve
            front_rgba = np.dstack([result, np.where(front_mask, 255, 0).astype(np.uint8)])
            Image.fromarray(front_rgba, "RGBA").save(
                blocks_dir / f"ai_front_overlay_{block.name}.png"
            )
    summary = {
        "model": MODEL,
        "licence": LICENCE,
        "windows_accepted": len(accepted),
        "windows_rejected": sum(1 for e in state["windows"].values() if not e["accepted"]),
        "coverage": round(covered / (info["width"] * info["height"]), 4),
        "composed_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    (ai_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    log.info("composed AI layer: %s", summary)
    return summary


def default_focus(area: AreaConfig) -> tuple[float, float]:
    return (area.center_lon, area.center_lat)
