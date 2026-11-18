import type { PointOfInterest } from "./manifest.ts";

const CURATED_RANK = Number.POSITIVE_INFINITY;

/** How many landmarks to show at a given image zoom (screen px per image px). */
export function markerBudget(imageZoom: number, total: number): number {
  if (imageZoom >= 0.35) return total;
  if (imageZoom >= 0.2) return Math.min(total, 60);
  if (imageZoom >= 0.1) return Math.min(total, 30);
  return Math.min(total, 15);
}

/** Ids of the most notable landmarks; curated ones (no rank) come first. */
export function visibleMarkerIds(
  pois: PointOfInterest[],
  imageZoom: number,
  selectedId: string | null,
): Set<string> {
  const ranked = [...pois].sort(
    (a, b) =>
      (b.rank ?? CURATED_RANK) - (a.rank ?? CURATED_RANK) || a.nameEn.localeCompare(b.nameEn),
  );
  const ids = new Set(ranked.slice(0, markerBudget(imageZoom, pois.length)).map((poi) => poi.id));
  if (selectedId) ids.add(selectedId);
  return ids;
}
