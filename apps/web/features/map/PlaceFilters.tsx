"use client";

import { type PlaceFilter, filterCounts } from "@/lib/filters";
import { type Lang, STRINGS } from "@/lib/i18n";
import type { PointOfInterest } from "@/lib/manifest";

interface PlaceFiltersProps {
  places: PointOfInterest[];
  active: PlaceFilter | null;
  lang: Lang;
  onChange: (id: string | null) => void;
}

export function PlaceFilters({
  places,
  active,
  lang,
  onChange,
}: PlaceFiltersProps) {
  const text = STRINGS[lang];
  const counts = filterCounts(places);
  if (counts.length < 2) return null;
  return (
    <div className="filters" role="group" aria-label={text.filterLabel}>
      <button
        type="button"
        className="filters__chip"
        aria-pressed={active === null}
        onClick={() => onChange(null)}
      >
        {text.filterAll}
        <span className="filters__count">{places.length}</span>
      </button>
      {counts.map(({ filter, count }) => (
        <button
          key={filter.id}
          type="button"
          className="filters__chip"
          aria-pressed={active?.id === filter.id}
          onClick={() => onChange(active?.id === filter.id ? null : filter.id)}
        >
          {lang === "th" ? filter.th : filter.en}
          <span className="filters__count">{count}</span>
        </button>
      ))}
    </div>
  );
}
