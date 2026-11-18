"""Geometric drift between a reference render and an AI-repainted copy.

Used to reject repainted windows that move roads, buildings or water.
"""

from __future__ import annotations

import numpy as np
from PIL import Image

EDGE_TOLERANCE_PX = 2
BLOCK_PX = 128
MAX_LOCAL_SHIFT_PX = 2
MIN_EDGE_RECALL = 0.9
MIN_MATCH_PEAK = 0.1
MAX_UNMATCHED_FRACTION = 0.3
MAX_REGISTRATION_PX = 8


def luminance_edges(image: Image.Image) -> np.ndarray:
    grey = np.asarray(image.convert("L"), dtype=np.float32)
    gx = np.zeros_like(grey)
    gy = np.zeros_like(grey)
    gx[:, 1:-1] = grey[:, 2:] - grey[:, :-2]
    gy[1:-1, :] = grey[2:, :] - grey[:-2, :]
    magnitude = np.hypot(gx, gy)
    return magnitude > max(24.0, float(np.percentile(magnitude, 85)))


def dilate(mask: np.ndarray, radius: int) -> np.ndarray:
    out = mask.copy()
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            out |= np.roll(np.roll(mask, dy, axis=0), dx, axis=1)
    return out


def phase_match(a: np.ndarray, b: np.ndarray) -> tuple[int, int, float]:
    """Shift (dx, dy) that best aligns b with a, and the correlation peak (0-1 confidence)."""
    fa = np.fft.fft2(a - a.mean())
    fb = np.fft.fft2(b - b.mean())
    cross = fa * np.conj(fb)
    cross /= np.abs(cross) + 1e-9
    correlation = np.abs(np.fft.ifft2(cross))
    peak = np.unravel_index(np.argmax(correlation), a.shape)
    dy, dx = (int(v) if v <= s // 2 else int(v - s) for v, s in zip(peak, a.shape, strict=True))
    return dx, dy, float(correlation.max())


def phase_shift(a: np.ndarray, b: np.ndarray) -> tuple[int, int]:
    dx, dy, _ = phase_match(a, b)
    return dx, dy


def register(reference: Image.Image, repainted: Image.Image) -> tuple[Image.Image, int, int]:
    """Undo a small uniform offset of the repainted image by whole pixels."""
    dx, dy, peak = phase_match(
        np.asarray(reference.convert("L"), np.float32),
        np.asarray(repainted.convert("L"), np.float32),
    )
    if peak < MIN_MATCH_PEAK or max(abs(dx), abs(dy)) > MAX_REGISTRATION_PX or (dx, dy) == (0, 0):
        return repainted, 0, 0
    shifted = np.roll(np.asarray(repainted), (dy, dx), axis=(0, 1)).copy()
    base = np.asarray(reference.convert(repainted.mode))
    if dy > 0:
        shifted[:dy] = base[:dy]
    elif dy < 0:
        shifted[dy:] = base[dy:]
    if dx > 0:
        shifted[:, :dx] = base[:, :dx]
    elif dx < 0:
        shifted[:, dx:] = base[:, dx:]
    return Image.fromarray(shifted, repainted.mode), dx, dy


def local_shifts(reference: np.ndarray, repainted: np.ndarray) -> tuple[list[tuple[int, int]], int]:
    """Confident per-block shifts, and the number of textured blocks with no confident match."""
    shifts = []
    unmatched = 0
    for top in range(0, reference.shape[0] - BLOCK_PX + 1, BLOCK_PX):
        for left in range(0, reference.shape[1] - BLOCK_PX + 1, BLOCK_PX):
            a = reference[top : top + BLOCK_PX, left : left + BLOCK_PX]
            b = repainted[top : top + BLOCK_PX, left : left + BLOCK_PX]
            if a.std() < 5:
                continue
            dx, dy, peak = phase_match(a, b)
            if peak < MIN_MATCH_PEAK:
                unmatched += 1
            else:
                shifts.append((dx, dy))
    return shifts, unmatched


def drift(reference: Image.Image, repainted: Image.Image) -> dict[str, float]:
    ref_edges = luminance_edges(reference)
    out_edges = luminance_edges(repainted)
    grey_reference = np.asarray(reference.convert("L"), np.float32)
    grey_repainted = np.asarray(repainted.convert("L"), np.float32)
    dx, dy = phase_shift(grey_reference, grey_repainted)
    blocks, unmatched = local_shifts(grey_reference, grey_repainted)
    worst = max((max(abs(x), abs(y)) for x, y in blocks), default=0)
    unmatched_fraction = unmatched / max(len(blocks) + unmatched, 1)
    recall = float(
        (ref_edges & dilate(out_edges, EDGE_TOLERANCE_PX)).sum() / max(ref_edges.sum(), 1)
    )
    precision = float(
        (out_edges & dilate(ref_edges, EDGE_TOLERANCE_PX)).sum() / max(out_edges.sum(), 1)
    )
    change = np.abs(
        np.asarray(reference, np.float32) - np.asarray(repainted.convert("RGB"), np.float32)
    ).mean()
    return {
        "mean_abs_change": round(float(change), 2),
        "shift_x_px": dx,
        "shift_y_px": dy,
        "edge_recall": round(recall, 3),
        "edge_precision": round(precision, 3),
        "max_local_shift_px": worst,
        "unmatched_fraction": round(unmatched_fraction, 3),
        "passes": bool(
            worst <= MAX_LOCAL_SHIFT_PX
            and recall >= MIN_EDGE_RECALL
            and unmatched_fraction <= MAX_UNMATCHED_FRACTION
        ),
    }
