"use client";

import { type RefObject, useId, useMemo, useState } from "react";

import { parseLatLon, type Point } from "@/lib/coords";
import { type Lang, placeName, STRINGS } from "@/lib/i18n";
import type { PointOfInterest } from "@/lib/manifest";
import { searchPois } from "@/lib/search";

import { PixelIcon } from "./icons";

interface PoiSearchProps {
  pois: PointOfInterest[];
  lang: Lang;
  inputRef: RefObject<HTMLInputElement | null>;
  onSelect: (id: string) => void;
  locate: (lat: number, lon: number) => Point | null;
  onGoTo: (point: Point) => void;
}

export function PoiSearch({ pois, lang, inputRef, onSelect, locate, onGoTo }: PoiSearchProps) {
  const text = STRINGS[lang];
  const [query, setQuery] = useState("");
  const inputId = useId();
  const coordinate = parseLatLon(query);
  const target = coordinate ? locate(coordinate.lat, coordinate.lon) : null;
  const results = useMemo(
    () => (parseLatLon(query) ? [] : searchPois(pois, query).slice(0, 8)),
    [pois, query],
  );
  const searching = query.trim() !== "";

  const finish = () => {
    setQuery("");
    inputRef.current?.blur();
  };
  const choose = (id: string) => {
    onSelect(id);
    finish();
  };
  const goTo = (point: Point) => {
    onGoTo(point);
    finish();
  };

  return (
    <search className="search">
      <label htmlFor={inputId} className="visually-hidden">
        {text.searchLabel}
      </label>
      <PixelIcon name="search" />
      <input
        ref={inputRef}
        id={inputId}
        type="search"
        value={query}
        placeholder={text.searchPlaceholder}
        autoComplete="off"
        enterKeyHint="search"
        onChange={(event) => setQuery(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Escape") setQuery("");
          if (event.key === "Enter") {
            event.preventDefault();
            if (event.nativeEvent.isComposing || event.keyCode === 229) return;
            if (target) goTo(target);
            else if (results[0]) choose(results[0].id);
          }
        }}
      />
      <kbd className="search__key" aria-hidden="true">
        /
      </kbd>
      <p className="visually-hidden" role="status">
        {coordinate
          ? target
            ? text.goToCoordinate(coordinate.lat.toFixed(5), coordinate.lon.toFixed(5))
            : text.outsideMap
          : searching
            ? text.resultsCount(results.length)
            : ""}
      </p>
      {coordinate && (
        <ul className="search__results">
          {target ? (
            <li>
              <button type="button" onClick={() => goTo(target)}>
                <span className="search__primary">
                  {text.goToCoordinate(coordinate.lat.toFixed(5), coordinate.lon.toFixed(5))}
                </span>
              </button>
            </li>
          ) : (
            <li className="search__empty">{text.outsideMap}</li>
          )}
        </ul>
      )}
      {searching && !coordinate && (
        <ul className="search__results">
          {results.length === 0 && <li className="search__empty">{text.searchNoResults}</li>}
          {results.map((poi) => {
            const names = placeName(poi, lang);
            return (
              <li key={poi.id}>
                <button type="button" onClick={() => choose(poi.id)}>
                  <span className="search__primary">{names.primary}</span>
                  {names.secondary && (
                    <span className="search__secondary" lang={lang === "th" ? "en" : "th"}>
                      {names.secondary}
                    </span>
                  )}
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </search>
  );
}
