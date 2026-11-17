"use client";

import { useState } from "react";

import { CreditsDialog } from "./CreditsDialog";
import { MapViewer } from "./MapViewer";
import { PoiPanel } from "./PoiPanel";
import { PoiSearch } from "./PoiSearch";
import { useAreaData } from "./useAreaData";

export function MapExplorer({ initialAreaId }: { initialAreaId: string | null }) {
  const [areaId, setAreaId] = useState(initialAreaId);
  const [selectedPoiId, setSelectedPoiId] = useState<string | null>(null);

  const { state, retry } = useAreaData(areaId);
  const data = state.status === "ready" ? state.data : null;
  const selectedPoi = data?.pois.find((poi) => poi.id === selectedPoiId) ?? null;

  const changeArea = (id: string) => {
    setSelectedPoiId(null);
    setAreaId(id);
    const url = new URL(window.location.href);
    url.searchParams.set("area", id);
    window.history.replaceState(null, "", url);
  };

  return (
    <div className="app">
      <header className="app__header">
        <h1>
          Pixel Bangkok
          {data && <span className="app__area">{data.manifest.name.en}</span>}
        </h1>
        {data && (
          <div className="app__tools">
            {data.areas.length > 1 && (
              <label className="area-select">
                <span className="visually-hidden">Map area</span>
                <select value={data.areaId} onChange={(event) => changeArea(event.target.value)}>
                  {data.areas.map((area) => (
                    <option key={area.id} value={area.id}>
                      {area.name.en}
                    </option>
                  ))}
                </select>
              </label>
            )}
            <PoiSearch pois={data.pois} onSelect={setSelectedPoiId} />
          </div>
        )}
      </header>

      <main className="app__main">
        {state.status === "loading" && (
          <p className="app__message" role="status">
            Loading map…
          </p>
        )}
        {state.status === "error" && (
          <div className="app__message" role="alert">
            <h2>The map could not be loaded</h2>
            <p>
              Map assets are missing or unreachable. If you are running locally, generate them with
              the pipeline first.
            </p>
            <p className="app__detail">{state.message}</p>
            <button type="button" onClick={retry}>
              Try again
            </button>
          </div>
        )}
        {data && (
          <>
            <MapViewer
              key={data.areaId}
              manifest={data.manifest}
              baseUrl={data.baseUrl}
              pois={data.pois}
              selectedPoiId={selectedPoiId}
              onSelectPoi={setSelectedPoiId}
            />
            {selectedPoi && <PoiPanel poi={selectedPoi} onClose={() => setSelectedPoiId(null)} />}
          </>
        )}
      </main>

      {data && (
        <footer className="app__footer">
          <p className="app__attributions">
            {data.manifest.attributions.map((attribution, index) => (
              <span key={attribution.url}>
                {index > 0 && " · "}
                <a href={attribution.url} target="_blank" rel="noreferrer">
                  {attribution.text}
                </a>
              </span>
            ))}
          </p>
          <CreditsDialog manifest={data.manifest} />
        </footer>
      )}
    </div>
  );
}
