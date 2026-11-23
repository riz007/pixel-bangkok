"use client";

import { type ReactNode, useEffect, useRef } from "react";

import { type Lang, placeName, STRINGS } from "@/lib/i18n";
import type { PointOfInterest } from "@/lib/manifest";

interface PlacesRailProps {
  id: string;
  places: PointOfInterest[];
  lang: Lang;
  selectedId: string | null;
  filters: ReactNode;
  onSelect: (id: string) => void;
  onClose: () => void;
}

/** The places list: a side panel on wide screens, a bottom sheet on phones. Places are numbered
 * in walking order, the same numbers as the pins. */
export function PlacesRail({
  id,
  places,
  lang,
  selectedId,
  filters,
  onSelect,
  onClose,
}: PlacesRailProps) {
  const text = STRINGS[lang];
  const listRef = useRef<HTMLOListElement>(null);

  useEffect(() => {
    if (!selectedId) return;
    listRef.current
      ?.querySelector<HTMLElement>(`[data-place="${selectedId}"]`)
      ?.scrollIntoView({ block: "nearest" });
  }, [selectedId]);

  return (
    <section id={id} className="places" aria-label={text.placesRail}>
      <header className="places__head">
        <h2 className="places__title">
          {text.places}
          <span className="places__count">
            {text.placesCount(places.length)}
          </span>
        </h2>
        <button
          type="button"
          className="icon-button"
          aria-label={text.closePlaces}
          onClick={onClose}
        >
          <span aria-hidden="true">×</span>
        </button>
      </header>
      {filters}
      <ol ref={listRef} className="places__list">
        {places.map((place, index) => {
          const names = placeName(place, lang);
          return (
            <li key={place.id} data-place={place.id}>
              <button
                type="button"
                className="plate"
                aria-current={place.id === selectedId ? "true" : undefined}
                onClick={() => onSelect(place.id)}
              >
                <span className="plate__number" aria-hidden="true">
                  {index + 1}
                </span>
                <span className="plate__names">
                  <span className="plate__primary">{names.primary}</span>
                  {names.secondary && (
                    <span
                      className="plate__secondary"
                      lang={lang === "th" ? "en" : "th"}
                    >
                      {names.secondary}
                    </span>
                  )}
                </span>
              </button>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
