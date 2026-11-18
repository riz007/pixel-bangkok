"""Back-to-front ordering of building footprints for the painter's algorithm.

Footprints are given in screen-aligned ground coordinates (u across the
screen, d depth away from the camera). Footprint A must be drawn before B when
a line of sight crosses both and meets B first. Pairs that cannot overlap on
screen (given each item's raised height in the same units as d) are skipped.
The constraints are sorted topologically; centroid depth only breaks ties and
cycles.
"""

from __future__ import annotations

import heapq
import logging
from collections.abc import Hashable, Sequence

import numpy as np
import shapely
from shapely.geometry import LineString, Polygon

log = logging.getLogger(__name__)

MIN_OVERLAP = 0.5
SAMPLE_FRACTIONS = (0.25, 0.5, 0.75)
TOLERANCE = 1e-6


def _depth_span(polygon: Polygon, u: float) -> tuple[float, float] | None:
    _, min_d, _, max_d = polygon.bounds
    hit = polygon.intersection(LineString([(u, min_d - 1), (u, max_d + 1)]))
    if hit.is_empty:
        return None
    return hit.bounds[1], hit.bounds[3]


def _is_behind(a: Polygon, b: Polygon) -> int:
    """Return 1 if a is behind b, -1 if b is behind a, 0 if neither occludes."""
    lo = max(a.bounds[0], b.bounds[0])
    hi = min(a.bounds[2], b.bounds[2])
    if hi - lo < MIN_OVERLAP:
        return 0
    votes = 0
    for fraction in SAMPLE_FRACTIONS:
        u = lo + (hi - lo) * fraction
        span_a, span_b = _depth_span(a, u), _depth_span(b, u)
        if span_a is None or span_b is None:
            continue
        if span_a[0] >= span_b[1] - TOLERANCE:
            votes += 1
        elif span_b[0] >= span_a[1] - TOLERANCE:
            votes -= 1
        elif span_a[0] != span_b[0]:
            votes += 1 if span_a[0] > span_b[0] else -1
    return (votes > 0) - (votes < 0)


def back_to_front(
    footprints: Sequence[Polygon],
    tie_breakers: Sequence[Hashable],
    raised: Sequence[float] | None = None,
    soft: Sequence[bool] | None = None,
) -> list[int]:
    """Return indices of `footprints` in drawing order, furthest first.

    `raised[i]` is how far item i extends above its footprint on screen, in d units.
    Two `soft` items (round symbols such as trees) get no constraint between them and fall
    back to depth order; constraints to other items are kept. This keeps dense canopy from
    producing millions of edges.
    """
    count = len(footprints)
    in_front: list[list[int]] = [[] for _ in range(count)]
    blockers = [0] * count
    if count == 0:
        return []
    extents = shapely.bounds(np.array(footprints, dtype=object))
    lift = np.full(count, np.inf) if raised is None else np.asarray(raised, dtype=float)
    low_u, high_u = extents[:, 0], extents[:, 2]
    low_d, high_d = extents[:, 1], extents[:, 3]
    high_v = high_d + lift
    is_soft = np.zeros(count, dtype=bool) if soft is None else np.asarray(soft, dtype=bool)
    order_u = np.argsort(low_u, kind="stable")
    sorted_low_u = low_u[order_u]

    def link(behind: int, front: int) -> None:
        in_front[behind].append(front)
        blockers[front] += 1

    for i in range(count):
        reach = np.searchsorted(sorted_low_u, high_u[i] - MIN_OVERLAP, side="right")
        rest = order_u[:reach]
        rest = rest[rest > i]
        if is_soft[i]:
            rest = rest[~is_soft[rest]]
        u_overlap = np.minimum(high_u[i], high_u[rest]) - np.maximum(low_u[i], low_u[rest])
        v_overlap = np.minimum(high_v[i], high_v[rest]) - np.maximum(low_d[i], low_d[rest])
        candidates = rest[(u_overlap >= MIN_OVERLAP) & (v_overlap > 0)]
        clearly_behind = low_d[i] >= high_d[candidates] - TOLERANCE
        clearly_front = low_d[candidates] >= high_d[i] - TOLERANCE
        for j in candidates[clearly_behind]:
            link(i, int(j))
        for j in candidates[clearly_front & ~clearly_behind]:
            link(int(j), i)
        for j in candidates[~clearly_behind & ~clearly_front]:
            j = int(j)
            relation = _is_behind(footprints[i], footprints[j])
            if relation > 0:
                link(i, j)
            elif relation < 0:
                link(j, i)

    def priority(index: int) -> tuple[float, Hashable, int]:
        return -footprints[index].centroid.y, tie_breakers[index], index

    ready = [priority(index) for index in range(count) if blockers[index] == 0]
    heapq.heapify(ready)
    remaining = set(range(count))
    order: list[int] = []
    cycles = 0
    while remaining:
        if ready:
            index = heapq.heappop(ready)[2]
            if index not in remaining:
                continue
        else:
            index = min(remaining, key=priority)
            cycles += 1
        remaining.discard(index)
        order.append(index)
        for front in in_front[index]:
            blockers[front] -= 1
            if blockers[front] == 0 and front in remaining:
                heapq.heappush(ready, priority(front))
    if cycles:
        log.warning("building draw order has %d occlusion cycle(s); broken by centroid", cycles)
    return order
