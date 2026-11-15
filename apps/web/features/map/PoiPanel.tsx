import type { PointOfInterest } from "@/lib/manifest";

import { categoryInfo } from "./poiCategories";

interface PoiPanelProps {
  poi: PointOfInterest;
  onClose: () => void;
}

export function PoiPanel({ poi, onClose }: PoiPanelProps) {
  const category = categoryInfo(poi.category);
  return (
    <aside className="poi-panel" aria-labelledby="poi-panel-title">
      <header className="poi-panel__header">
        <p className="poi-panel__category">
          <span aria-hidden="true">{category.glyph}</span> {category.label}
        </p>
        <button type="button" className="icon-button" aria-label="Close details" onClick={onClose}>
          <span aria-hidden="true">×</span>
        </button>
      </header>
      <h2 id="poi-panel-title">{poi.nameEn}</h2>
      {poi.nameTh && (
        <p className="poi-panel__thai" lang="th">
          {poi.nameTh}
        </p>
      )}
      <p>{poi.description}</p>
      <dl className="poi-panel__meta">
        <dt>Coordinates</dt>
        <dd>
          {poi.lat.toFixed(5)}° N, {poi.lon.toFixed(5)}° E
        </dd>
        {poi.source && (
          <>
            <dt>Source</dt>
            <dd>
              {poi.sourceUrl ? (
                <a href={poi.sourceUrl} target="_blank" rel="noreferrer">
                  {poi.source}
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
