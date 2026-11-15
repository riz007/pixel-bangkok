"use client";

import { useCallback, useEffect, useState } from "react";

import {
  type AreaSummary,
  DataError,
  parseAreaIndex,
  parseManifest,
  parsePois,
  type PointOfInterest,
  type TileManifest,
} from "@/lib/manifest";

export const MAP_ASSETS_URL = (process.env.NEXT_PUBLIC_MAP_ASSETS_URL ?? "/maps").replace(
  /\/$/,
  "",
);

export interface AreaData {
  areas: AreaSummary[];
  areaId: string;
  baseUrl: string;
  manifest: TileManifest;
  pois: PointOfInterest[];
}

export type AreaState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; data: AreaData };

async function fetchJson(url: string, signal: AbortSignal): Promise<unknown> {
  const response = await fetch(url, { signal });
  if (!response.ok) throw new DataError(`${url} responded with ${response.status}`);
  return response.json();
}

async function loadArea(requestedId: string | null, signal: AbortSignal): Promise<AreaData> {
  const areas = parseAreaIndex(await fetchJson(`${MAP_ASSETS_URL}/index.json`, signal));
  const area = areas.find((entry) => entry.id === requestedId) ?? areas[0];
  if (!area) throw new DataError("no map areas have been published");
  const baseUrl = `${MAP_ASSETS_URL}/${encodeURIComponent(area.id)}`;
  const [manifestJson, poisJson] = await Promise.all([
    fetchJson(`${baseUrl}/manifest.json`, signal),
    fetchJson(`${baseUrl}/pois.json`, signal),
  ]);
  const manifest = parseManifest(manifestJson);
  return { areas, areaId: area.id, baseUrl, manifest, pois: parsePois(poisJson, manifest) };
}

export function useAreaData(requestedId: string | null): { state: AreaState; retry: () => void } {
  const [state, setState] = useState<AreaState>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    loadArea(requestedId, controller.signal)
      .then((data) => setState({ status: "ready", data }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        console.error("Failed to load map data", error);
        setState({
          status: "error",
          message: error instanceof Error ? error.message : "unknown error",
        });
      });
    return () => controller.abort();
  }, [requestedId, attempt]);

  const retry = useCallback(() => {
    setState({ status: "loading" });
    setAttempt((value) => value + 1);
  }, []);

  return { state, retry };
}
