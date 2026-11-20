import type { PointOfInterest } from "./manifest.ts";

export interface PlaceFilter {
  id: string;
  categories: string[];
  en: string;
  th: string;
}

/** Place groups shown as filter chips; categories come from the pipeline's POI stage. */
export const PLACE_FILTERS: PlaceFilter[] = [
  {
    id: "worship",
    categories: ["temple"],
    en: "Places of worship",
    th: "ศาสนสถาน",
  },
  {
    id: "transit",
    categories: ["transit", "pier"],
    en: "Transit",
    th: "การเดินทาง",
  },
  {
    id: "landmarks",
    categories: ["landmark", "historic"],
    en: "Landmarks",
    th: "สถานที่สำคัญ",
  },
  { id: "museums", categories: ["museum"], en: "Museums", th: "พิพิธภัณฑ์" },
  { id: "parks", categories: ["park"], en: "Parks", th: "สวน" },
  { id: "markets", categories: ["market"], en: "Markets", th: "ตลาด" },
  {
    id: "neighbourhoods",
    categories: ["neighbourhood"],
    en: "Neighbourhoods",
    th: "ย่าน",
  },
];

export function findFilter(id: string | null): PlaceFilter | null {
  return PLACE_FILTERS.find((filter) => filter.id === id) ?? null;
}

/** Places in the filter; the selected place always stays so a search result never vanishes. */
export function filterPlaces<
  T extends Pick<PointOfInterest, "id" | "category">,
>(
  places: T[],
  filter: PlaceFilter | null,
  selectedId: string | null = null,
): T[] {
  if (!filter) return places;
  return places.filter(
    (place) =>
      filter.categories.includes(place.category) || place.id === selectedId,
  );
}

/** Filters with at least one place, with counts, in display order. */
export function filterCounts<T extends Pick<PointOfInterest, "category">>(
  places: T[],
): { filter: PlaceFilter; count: number }[] {
  return PLACE_FILTERS.map((filter) => ({
    filter,
    count: places.filter((place) => filter.categories.includes(place.category))
      .length,
  })).filter((entry) => entry.count > 0);
}
