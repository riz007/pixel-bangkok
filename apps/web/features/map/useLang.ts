"use client";

import { useCallback, useSyncExternalStore } from "react";

import { detectLang, type Lang } from "@/lib/i18n";

const KEY = "pixel-bangkok:lang";
const EVENT = "pixel-bangkok:lang";

function read(): Lang {
  try {
    const stored = window.localStorage.getItem(KEY);
    if (stored === "th" || stored === "en") return stored;
  } catch {
    // Storage can be unavailable (private mode); fall back to the browser language.
  }
  return detectLang(navigator.languages ?? [navigator.language]);
}

function subscribe(onChange: () => void) {
  window.addEventListener(EVENT, onChange);
  window.addEventListener("storage", onChange);
  return () => {
    window.removeEventListener(EVENT, onChange);
    window.removeEventListener("storage", onChange);
  };
}

export function useLang(): [Lang, (lang: Lang) => void] {
  const lang = useSyncExternalStore(subscribe, read, () => "th" as Lang);
  const setLang = useCallback((next: Lang) => {
    try {
      window.localStorage.setItem(KEY, next);
    } catch {
      // Not persisted; still switch for this visit.
    }
    window.dispatchEvent(new Event(EVENT));
    document.documentElement.lang = next;
  }, []);
  return [lang, setLang];
}
