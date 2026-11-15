"use client";

import { useId, useMemo, useState } from "react";

import type { PointOfInterest } from "@/lib/manifest";
import { searchPois } from "@/lib/search";

import { categoryInfo } from "./poiCategories";

interface PoiSearchProps {
  pois: PointOfInterest[];
  onSelect: (id: string) => void;
}

export function PoiSearch({ pois, onSelect }: PoiSearchProps) {
  const [query, setQuery] = useState("");
  const inputId = useId();
  const results = useMemo(() => searchPois(pois, query), [pois, query]);
  const searching = query.trim() !== "";

  return (
    <search className="poi-search">
      <label htmlFor={inputId} className="visually-hidden">
        Search places in Thai or English
      </label>
      <input
        id={inputId}
        type="search"
        value={query}
        placeholder="Search places · ค้นหาสถานที่"
        autoComplete="off"
        onChange={(event) => setQuery(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Escape") setQuery("");
        }}
      />
      <p className="visually-hidden" role="status">
        {searching ? `${results.length} ${results.length === 1 ? "place" : "places"} found` : ""}
      </p>
      {searching && (
        <ul className="poi-search__results">
          {results.length === 0 && <li className="poi-search__empty">No curated places match.</li>}
          {results.map((poi) => (
            <li key={poi.id}>
              <button
                type="button"
                onClick={() => {
                  onSelect(poi.id);
                  setQuery("");
                }}
              >
                <span aria-hidden="true">{categoryInfo(poi.category).glyph}</span>
                <span>
                  {poi.nameEn}
                  {poi.nameTh && (
                    <span className="poi-search__thai" lang="th">
                      {poi.nameTh}
                    </span>
                  )}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </search>
  );
}
