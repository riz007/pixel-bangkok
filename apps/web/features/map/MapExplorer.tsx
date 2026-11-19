"use client";

import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";

import { imageToLonLat, lonLatToImage, type Point } from "@/lib/coords";
import { STRINGS } from "@/lib/i18n";
import { tourOrder } from "@/lib/tour";

import { AboutDialog } from "./AboutDialog";
import { ConsentBanner } from "./ConsentBanner";
import { toggleFullscreen } from "./fullscreen";
import { PixelIcon } from "./icons";
import { type MapCommands, MapViewer } from "./MapViewer";
import { PlacePanel } from "./PlacePanel";
import { PlacesRail } from "./PlacesRail";
import { PoiSearch } from "./PoiSearch";
import { useAreaData } from "./useAreaData";
import { useLang } from "./useLang";

const REDUCED_MOTION_QUERY = "(prefers-reduced-motion: reduce)";

function subscribeReducedMotion(onChange: () => void) {
  const query = window.matchMedia(REDUCED_MOTION_QUERY);
  query.addEventListener("change", onChange);
  return () => query.removeEventListener("change", onChange);
}

function isTyping(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName);
}

interface MapExplorerProps {
  initialAreaId: string | null;
  initialPlaceId: string | null;
}

export function MapExplorer({ initialAreaId, initialPlaceId }: MapExplorerProps) {
  const [lang, setLang] = useLang();
  const text = STRINGS[lang];
  const [areaId, setAreaId] = useState(initialAreaId);
  const [selectedPoiId, setSelectedPoiId] = useState<string | null>(initialPlaceId);
  const [railOpen, setRailOpen] = useState(true);
  const [aiOn, setAiOn] = useState(true);
  const [showLabels, setShowLabels] = useState(false);
  const [animationAvailable, setAnimationAvailable] = useState(false);
  const reducedMotion = useSyncExternalStore(
    subscribeReducedMotion,
    () => window.matchMedia(REDUCED_MOTION_QUERY).matches,
    () => false,
  );
  const [playChoice, setPlayChoice] = useState<boolean | null>(null);
  const playing = playChoice ?? !reducedMotion;
  const [toast, setToast] = useState<string | null>(null);
  const [pin, setPin] = useState<Point | null>(null);
  const commandsRef = useRef<MapCommands | null>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const aboutRef = useRef<HTMLDialogElement>(null);

  const { state, retry } = useAreaData(areaId);
  const data = state.status === "ready" ? state.data : null;
  const tour = useMemo(() => (data ? tourOrder(data.pois) : []), [data]);
  const tourNumbers = useMemo(
    () => new Map(tour.map((poi, index) => [poi.id, index + 1] as const)),
    [tour],
  );
  const selectedPoi = data?.pois.find((poi) => poi.id === selectedPoiId) ?? null;
  const hasAi = Boolean(data?.manifest.ai);

  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);

  const updateUrl = useCallback((params: Record<string, string | null>) => {
    const url = new URL(window.location.href);
    for (const [key, value] of Object.entries(params)) {
      if (value === null) url.searchParams.delete(key);
      else url.searchParams.set(key, value);
    }
    window.history.replaceState(null, "", url);
  }, []);

  const select = useCallback(
    (id: string | null) => {
      setSelectedPoiId(id);
      updateUrl({ place: id });
    },
    [updateUrl],
  );

  const changeArea = (id: string) => {
    setSelectedPoiId(null);
    setPin(null);
    setAreaId(id);
    updateUrl({ area: id, place: null });
  };

  const goTo = (point: Point) => {
    select(null);
    setPin(point);
    commandsRef.current?.goTo(point);
  };

  const report = () => {
    const centre = commandsRef.current?.center();
    const location = data && centre ? imageToLonLat(data.manifest, centre) : null;
    const hash = location
      ? `#map=18/${location.lat.toFixed(5)}/${location.lon.toFixed(5)}`
      : "";
    window.open(`https://www.openstreetmap.org/note/new${hash}`, "_blank", "noopener,noreferrer");
  };

  const share = async () => {
    const url = window.location.href;
    const title = `${text.appName} · ${text.cityName}`;
    try {
      if (navigator.share && window.matchMedia("(pointer: coarse)").matches) {
        await navigator.share({ title, url });
        return;
      }
      await navigator.clipboard.writeText(url);
      setToast(text.linkCopied);
      window.setTimeout(() => setToast(null), 2200);
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") return;
      setToast(url);
      window.setTimeout(() => setToast(null), 5000);
    }
  };

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.metaKey || event.ctrlKey || event.altKey || isTyping(event.target)) return;
      if (aboutRef.current?.open) return;
      const key = event.key.toLowerCase();
      if (key === "/") {
        event.preventDefault();
        searchRef.current?.focus();
      } else if (key === "p") setRailOpen((open) => !open);
      else if (key === "a" && hasAi) setAiOn((on) => !on);
      else if (key === "l") setShowLabels((on) => !on);
      else if (key === "t" && animationAvailable) setPlayChoice(!playing);
      else if (key === "f") toggleFullscreen();
      else if (key === "+" || key === "=") commandsRef.current?.zoomBy(1.5);
      else if (key === "-" || key === "_") commandsRef.current?.zoomBy(1 / 1.5);
      else if (key === "h" || key === "0") commandsRef.current?.home();
      else if (key === "escape") select(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [hasAi, animationAvailable, playing, select]);

  return (
    <div className="app" data-rail={railOpen && tour.length > 0 ? "open" : "closed"}>
      <header className="topbar">
        <h1 className="title">
          <button
            type="button"
            className="title__plate"
            aria-label={`${text.appName}, ${text.cityName}. ${text.about}`}
            onClick={() => aboutRef.current?.showModal()}
          >
            <span className="title__th" lang="th">
              กรุงเทพมหานคร
            </span>
            <span className="title__en" lang="en">
              Pixel Bangkok
            </span>
          </button>
        </h1>

        {data && (
          <PoiSearch
            pois={data.pois}
            lang={lang}
            inputRef={searchRef}
            onSelect={select}
            locate={(lat, lon) => lonLatToImage(data.manifest, lon, lat)}
            onGoTo={goTo}
          />
        )}

        <nav className="tools" aria-label={text.mapTools}>
          {data && data.areas.length > 1 && (
            <label className="tools__area">
              <span className="visually-hidden">{text.mapArea}</span>
              <select value={data.areaId} onChange={(event) => changeArea(event.target.value)}>
                {data.areas.map((area) => (
                  <option key={area.id} value={area.id}>
                    {lang === "th" && area.name.th ? area.name.th : area.name.en}
                  </option>
                ))}
              </select>
            </label>
          )}
          <button
            type="button"
            className="tool"
            aria-pressed={railOpen}
            onClick={() => setRailOpen(!railOpen)}
          >
            <PixelIcon name="places" />
            <span>{text.places}</span>
          </button>
          {hasAi && (
            <button
              type="button"
              className="tool"
              aria-pressed={aiOn}
              aria-label={aiOn ? text.aiOnLabel : text.aiOffLabel}
              onClick={() => setAiOn(!aiOn)}
            >
              <PixelIcon name="ai" />
              <span aria-hidden="true">{text.aiArt}</span>
            </button>
          )}
          <button
            type="button"
            className="tool"
            aria-pressed={showLabels}
            onClick={() => setShowLabels(!showLabels)}
          >
            <PixelIcon name="labels" />
            <span>{text.labels}</span>
          </button>
          {animationAvailable && (
            <button
              type="button"
              className="tool"
              aria-pressed={playing}
              aria-label={playing ? text.trafficOnLabel : text.trafficOffLabel}
              onClick={() => setPlayChoice(!playing)}
            >
              <PixelIcon name={playing ? "pause" : "play"} />
              <span aria-hidden="true">{text.traffic}</span>
            </button>
          )}
          <button type="button" className="tool" onClick={share}>
            <PixelIcon name="share" />
            <span>{text.share}</span>
          </button>
          <button type="button" className="tool" aria-label={text.reportLabel} onClick={report}>
            <PixelIcon name="report" />
            <span aria-hidden="true">{text.report}</span>
          </button>
          <button type="button" className="tool" onClick={() => aboutRef.current?.showModal()}>
            <PixelIcon name="about" />
            <span>{text.about}</span>
          </button>
          <button
            type="button"
            className="tool tool--lang"
            aria-label={text.languageLabel}
            onClick={() => setLang(lang === "th" ? "en" : "th")}
          >
            <span lang={lang === "th" ? "en" : "th"}>{text.language}</span>
          </button>
        </nav>
      </header>

      <main className="stage">
        {state.status === "loading" && (
          <p className="stage__message" role="status">
            {text.loadingMap}
          </p>
        )}
        {state.status === "error" && (
          <div className="stage__message" role="alert">
            <h2>{text.mapUnavailable}</h2>
            <p>{text.mapUnavailableHint}</p>
            <p className="stage__detail">{state.message}</p>
            <button type="button" onClick={retry}>
              {text.tryAgain}
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
              onSelectPoi={select}
              aiOn={aiOn}
              playing={playing}
              showLabels={showLabels}
              lang={lang}
              tourNumbers={tourNumbers}
              commandsRef={commandsRef}
              onAnimationAvailable={setAnimationAvailable}
              pin={pin}
            />
            {selectedPoi && (
              <PlacePanel
                poi={selectedPoi}
                number={tourNumbers.get(selectedPoi.id)}
                lang={lang}
                onClose={() => select(null)}
              />
            )}
            {railOpen && (
              <PlacesRail
                places={tour}
                baseUrl={data.baseUrl}
                version={
                  data.manifest.ai
                    ? `${data.manifest.contentVersion}-${data.manifest.ai.version}`
                    : data.manifest.contentVersion
                }
                lang={lang}
                selectedId={selectedPoiId}
                onSelect={select}
              />
            )}
            <p className="credit">
              {data.manifest.attributions.map((attribution, index) => (
                <span key={attribution.url}>
                  {index > 0 && ", "}
                  <a href={attribution.url} target="_blank" rel="noreferrer">
                    {attribution.text}
                  </a>
                </span>
              ))}
            </p>
            <AboutDialog dialogRef={aboutRef} manifest={data.manifest} lang={lang} />
          </>
        )}
        <ConsentBanner lang={lang} />
        <p className="toast" role="status" aria-live="polite">
          {toast}
        </p>
      </main>
    </div>
  );
}
