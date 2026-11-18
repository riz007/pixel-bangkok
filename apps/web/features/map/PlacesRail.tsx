"use client";

import { useEffect, useRef } from "react";

import { type Lang, placeName, STRINGS } from "@/lib/i18n";
import type { PointOfInterest } from "@/lib/manifest";

interface PlacesRailProps {
  places: PointOfInterest[];
  baseUrl: string;
  version: string;
  lang: Lang;
  selectedId: string | null;
  onSelect: (id: string) => void;
}

export function PlacesRail({ places, baseUrl, version, lang, selectedId, onSelect }: PlacesRailProps) {
  const text = STRINGS[lang];
  const trackRef = useRef<HTMLOListElement>(null);

  useEffect(() => {
    if (!selectedId) return;
    const item = trackRef.current?.querySelector<HTMLElement>(`[data-place="${selectedId}"]`);
    const track = trackRef.current;
    if (!item || !track) return;
    const offset = item.offsetLeft - (track.clientWidth - item.clientWidth) / 2;
    track.scrollTo({ left: offset });
  }, [selectedId]);

  const step = (direction: 1 | -1) => {
    if (places.length === 0) return;
    const index = places.findIndex((place) => place.id === selectedId);
    const next = index === -1 ? 0 : (index + direction + places.length) % places.length;
    onSelect(places[next]!.id);
  };

  if (places.length === 0) return null;

  return (
    <section className="rail" aria-roledescription="carousel" aria-label={text.placesRail}>
      <button type="button" className="rail__step" aria-label={text.previousPlace} onClick={() => step(-1)}>
        <span aria-hidden="true">‹</span>
      </button>
      <ol ref={trackRef} className="rail__track">
        {places.map((place, index) => {
          const names = placeName(place, lang);
          const current = place.id === selectedId;
          return (
            <li
              key={place.id}
              data-place={place.id}
              aria-roledescription="slide"
              aria-label={text.placeOf(index + 1, places.length)}
            >
              <button
                type="button"
                className="plate"
                aria-current={current ? "true" : undefined}
                onClick={() => onSelect(place.id)}
              >
                {place.thumbnail && (
                  // Thumbnails are small pre-cropped WebP files; next/image adds nothing here.
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    className="plate__image"
                    src={`${baseUrl}/${place.thumbnail}?v=${version}`}
                    alt=""
                    width={180}
                    height={110}
                    loading="lazy"
                    decoding="async"
                  />
                )}
                <span className="plate__sign">
                  <span className="plate__number" aria-hidden="true">
                    {index + 1}
                  </span>
                  <span className="plate__names">
                    <span className="plate__primary">{names.primary}</span>
                    {names.secondary && (
                      <span className="plate__secondary" lang={lang === "th" ? "en" : "th"}>
                        {names.secondary}
                      </span>
                    )}
                  </span>
                </span>
              </button>
            </li>
          );
        })}
      </ol>
      <button type="button" className="rail__step" aria-label={text.nextPlace} onClick={() => step(1)}>
        <span aria-hidden="true">›</span>
      </button>
    </section>
  );
}
