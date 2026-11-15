import type { PointOfInterest } from "./manifest";

export function normaliseQuery(value: string): string {
  return value
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/\s+/g, " ")
    .trim();
}

function score(poi: PointOfInterest, query: string): number {
  const names = [poi.nameEn, poi.nameTh ?? "", ...poi.aliases].map(normaliseQuery);
  if (names.some((name) => name === query)) return 3;
  if (names.some((name) => name.startsWith(query))) return 2;
  if (names.some((name) => name.includes(query))) return 1;
  return normaliseQuery(poi.category) === query ? 1 : 0;
}

export function searchPois(pois: PointOfInterest[], rawQuery: string): PointOfInterest[] {
  const query = normaliseQuery(rawQuery);
  if (query === "") return [];
  return pois
    .map((poi) => ({ poi, score: score(poi, query) }))
    .filter((entry) => entry.score > 0)
    .sort((a, b) => b.score - a.score || a.poi.nameEn.localeCompare(b.poi.nameEn))
    .map((entry) => entry.poi);
}
