"use client";

import { useSyncExternalStore } from "react";

import { type Lang, STRINGS } from "@/lib/i18n";

const SEEN_KEY = "pixel-bangkok:hint-seen";
const listeners = new Set<() => void>();

function seen(): boolean {
  try {
    return window.localStorage.getItem(SEEN_KEY) === "1";
  } catch {
    return false;
  }
}

/** Remembers that the visitor has found their way around, so the hint shows only once. */
export function markHintSeen() {
  try {
    window.localStorage.setItem(SEEN_KEY, "1");
  } catch {}
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function FirstVisitHint({
  lang,
  onBrowse,
}: {
  lang: Lang;
  onBrowse: () => void;
}) {
  const hidden = useSyncExternalStore(subscribe, seen, () => true);
  if (hidden) return null;
  const text = STRINGS[lang];
  return (
    <div className="hint" role="status">
      <p>{text.hint}</p>
      <button
        type="button"
        className="hint__browse"
        onClick={() => {
          markHintSeen();
          onBrowse();
        }}
      >
        {text.hintPlaces}
      </button>
      <button
        type="button"
        className="icon-button"
        aria-label={text.dismiss}
        onClick={markHintSeen}
      >
        <span aria-hidden="true">×</span>
      </button>
    </div>
  );
}
