import { type Lang, lineLabel, placeName, STRINGS } from "@/lib/i18n";
import type { PointOfInterest } from "@/lib/manifest";

import { categoryInfo } from "./poiCategories";

interface PlacePanelProps {
  poi: PointOfInterest;
  number: number | undefined;
  lang: Lang;
  thumbnailUrl: string | null;
  onClose: () => void;
}

export function PlacePanel({
  poi,
  number,
  lang,
  thumbnailUrl,
  onClose,
}: PlacePanelProps) {
  const text = STRINGS[lang];
  const names = placeName(poi, lang);
  const category = categoryInfo(poi.category);
  return (
    <aside className="panel" aria-labelledby="panel-title">
      {thumbnailUrl && (
        // A small pre-cropped WebP of the place on the map; next/image adds nothing here.
        // eslint-disable-next-line @next/next/no-img-element
        <img
          key={thumbnailUrl}
          className="panel__image"
          src={thumbnailUrl}
          alt=""
          width={180}
          height={110}
          decoding="async"
        />
      )}
      <div className="panel__sign">
        {number !== undefined && (
          <span className="panel__number" aria-hidden="true">
            {number}
          </span>
        )}
        <div>
          <h2 id="panel-title" className="panel__primary">
            {names.primary}
          </h2>
          {names.secondary && (
            <p className="panel__secondary" lang={lang === "th" ? "en" : "th"}>
              {names.secondary}
            </p>
          )}
        </div>
        <button
          type="button"
          className="panel__close"
          aria-label={text.close}
          onClick={onClose}
        >
          <span aria-hidden="true">×</span>
        </button>
      </div>
      <p className="panel__category">
        <span aria-hidden="true">{category.glyph}</span> {category.label}
      </p>
      {poi.line && <p className="panel__line">{lineLabel(poi.line, lang)}</p>}
      {poi.description && (
        <p className="panel__description">{poi.description}</p>
      )}
      <dl className="panel__meta">
        <dt>{text.coordinates}</dt>
        <dd>
          {poi.lat.toFixed(5)}° N, {poi.lon.toFixed(5)}° E
        </dd>
        {poi.source && (
          <>
            <dt>{text.source}</dt>
            <dd>
              {poi.sourceUrl ? (
                <a href={poi.sourceUrl} target="_blank" rel="noreferrer">
                  {text.readMore}
                </a>
              ) : (
                poi.source
              )}
            </dd>
          </>
        )}
      </dl>
    </aside>
  );
}
