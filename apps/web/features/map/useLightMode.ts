"use client";

import { useEffect, useState, useSyncExternalStore } from "react";

import { type LightMode, LIGHT_MODES, type Sky, skyFor } from "@/lib/daylight";

const KEY = "pixel-bangkok:light";
const listeners = new Set<() => void>();

function read(): LightMode {
  try {
    const value = window.localStorage.getItem(KEY);
    return LIGHT_MODES.includes(value as LightMode)
      ? (value as LightMode)
      : "auto";
  } catch {
    return "auto";
  }
}

function write(mode: LightMode) {
  try {
    window.localStorage.setItem(KEY, mode);
  } catch {}
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** The visitor's day and night choice (remembered on this device) and the sky it gives now,
 * re-checked every minute so dusk arrives on its own. */
export function useLightMode(): {
  mode: LightMode;
  setMode: (mode: LightMode) => void;
  sky: Sky;
  now: Date;
} {
  const mode = useSyncExternalStore(subscribe, read, () => "auto" as const);
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 60_000);
    return () => window.clearInterval(timer);
  }, []);
  return { mode, setMode: write, sky: skyFor(mode, now), now };
}
