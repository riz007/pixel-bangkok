import { readFile } from "node:fs/promises";
import path from "node:path";

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
