"use client";

import { useEffect, useState } from "react";

import type { Weather } from "@/lib/weather";

const REFRESH_MS = 10 * 60_000;

/** Current Bangkok weather from the site's own cached route; null while loading, when turned
 * off, or when the weather service is unavailable (the map works the same without it). */
export function useWeather(enabled: boolean): Weather | null {
  const [weather, setWeather] = useState<Weather | null>(null);
  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    const load = async () => {
      try {
        const response = await fetch("/api/weather");
        if (!response.ok) throw new Error(String(response.status));
        const data = (await response.json()) as Weather;
        if (!cancelled) setWeather(data);
      } catch {
        if (!cancelled) setWeather(null);
      }
    };
    void load();
    const timer = window.setInterval(load, REFRESH_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [enabled]);
  return enabled ? weather : null;
}
