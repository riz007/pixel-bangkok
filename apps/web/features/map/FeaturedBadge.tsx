"use client";

import { useSyncExternalStore } from "react";

import { type Lang, STRINGS } from "@/lib/i18n";

const HIDDEN_KEY = "pixel-bangkok:featured-badge-hidden";
const listeners = new Set<() => void>();

function isHidden(): boolean {
  try {
    return window.localStorage.getItem(HIDDEN_KEY) === "1";
  } catch {
    return false;
  }
}

function hide() {
  try {
    window.localStorage.setItem(HIDDEN_KEY, "1");
  } catch {}
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function FeaturedBadge({ lang }: { lang: Lang }) {
  const hidden = useSyncExternalStore(subscribe, isHidden, () => true);
  if (hidden) return null;
  const text = STRINGS[lang];
  return (
    <div className="featured">
      <a
        href="https://isometriccities.com/cities/bangkok/"
        target="_blank"
        rel="noopener"
        title="Featured on Isometric Cities"
      >
        {/* eslint-disable-next-line @next/next/no-img-element -- static badge from the listing site */}
        <img src="/isometric-cities-badge.svg" alt="Featured on Isometric Cities" width={200} height={48} />
      </a>
      <button type="button" className="featured__hide" aria-label={text.featuredHide} onClick={hide}>
        <span aria-hidden="true">×</span>
      </button>
    </div>
  );
}
