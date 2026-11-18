import type { PointOfInterest } from "./manifest.ts";

const CURATED_RANK = Number.POSITIVE_INFINITY;

/**
 * The most notable landmarks as a walking route: start at the northernmost and
 * repeatedly visit the nearest unvisited one (in map pixels).
 */
export function tourOrder(pois: PointOfInterest[], limit = 32): PointOfInterest[] {
  const candidates = [...pois]
    .sort(
      (a, b) =>
        (b.rank ?? CURATED_RANK) - (a.rank ?? CURATED_RANK) || a.id.localeCompare(b.id),
    )
    .slice(0, limit);
  if (candidates.length === 0) return [];
  const remaining = new Set(candidates);
  let current = candidates.reduce((best, poi) =>
    poi.lat > best.lat || (poi.lat === best.lat && poi.id < best.id) ? poi : best,
  );
  const route: PointOfInterest[] = [];
  while (remaining.size > 0) {
    route.push(current);
    remaining.delete(current);
    let next: PointOfInterest | null = null;
    let nearest = Number.POSITIVE_INFINITY;
    for (const poi of remaining) {
      const distance = Math.hypot(poi.image.x - current.image.x, poi.image.y - current.image.y);
      if (distance < nearest || (distance === nearest && next && poi.id < next.id)) {
        nearest = distance;
        next = poi;
      }
    }
    if (!next) break;
    current = next;
  }
  return route;
}
