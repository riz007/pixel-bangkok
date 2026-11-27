import { readFile } from "node:fs/promises";
import path from "node:path";

import { parseManifest, parsePois, type PointOfInterest } from "./manifest";
import { assetsBase } from "./site";

export interface AreaEntry {
  id: string;
  name: { en: string; th?: string | null };
}

export interface PlaceEntry {
  id: string;
  name_en: string;
  name_th: string | null;
  category: string;
  description: string;
  lat: number;
  lon: number;
  rank: number | null;
}

const RELATIVE_BASE = (process.env.NEXT_PUBLIC_MAP_ASSETS_URL ?? "/maps").replace(/\/+$/, "");

/** Published map JSON: from object storage in production, from public/ when served locally. */
async function readJson<T>(file: string): Promise<T | null> {
  try {
    if (!RELATIVE_BASE.startsWith("http")) {
      const local = path.join(/* turbopackIgnore: true */ process.cwd(), "public", RELATIVE_BASE, file);
      return JSON.parse(await readFile(local, "utf-8")) as T;
    }
    const response = await fetch(`${assetsBase()}/${file}`, { next: { revalidate: 3600 } });
    return response.ok ? ((await response.json()) as T) : null;
  } catch {
    return null;
  }
}

export async function areas(): Promise<AreaEntry[]> {
  const index = await readJson<{ areas: AreaEntry[] }>("index.json");
  return index?.areas ?? [];
}

export async function places(areaId: string): Promise<PlaceEntry[]> {
  const data = await readJson<{ pois: PlaceEntry[] }>(`${encodeURIComponent(areaId)}/pois.json`);
  return data?.pois ?? [];
}

/** The one address Google should index for a place: the first published area (in index order)
 * that contains it. The same place in other areas points here, so each place is one page. */
export async function canonicalArea(placeId: string): Promise<string | null> {
  for (const area of await areas()) {
    if ((await places(area.id)).some((place) => place.id === placeId)) return area.id;
  }
  return null;
}

/** Every place once, with the area its canonical address uses. */
export async function canonicalPlaces(): Promise<{ areaId: string; place: PlaceEntry }[]> {
  const seen = new Set<string>();
  const result: { areaId: string; place: PlaceEntry }[] = [];
  for (const area of await areas()) {
    for (const place of await places(area.id)) {
      if (seen.has(place.id)) continue;
      seen.add(place.id);
      result.push({ areaId: area.id, place });
    }
  }
  return result;
}

/** A place's card as the viewer shows it, read on the server so the first HTML already carries
 * the place's name, description and details for visitors and search engines. */
export async function placeCard(
  areaId: string,
  placeId: string,
): Promise<{ poi: PointOfInterest; thumbnailUrl: string | null } | null> {
  const area = encodeURIComponent(areaId);
  const [manifestJson, poisJson] = await Promise.all([
    readJson<unknown>(`${area}/manifest.json`),
    readJson<unknown>(`${area}/pois.json`),
  ]);
  if (!manifestJson || !poisJson) return null;
  try {
    const manifest = parseManifest(manifestJson);
    const poi = parsePois(poisJson, manifest).find((entry) => entry.id === placeId);
    if (!poi) return null;
    const thumbnailUrl = poi.thumbnail
      ? `${RELATIVE_BASE}/${area}/${poi.thumbnail}?v=${manifest.contentVersion}-plain`
      : null;
    return { poi, thumbnailUrl };
  } catch {
    return null;
  }
}
